"""Tier-2 manually registered platforms (ZCode / Qoder / WorkBuddy, ...).

A :class:`ManualProvider` never opens a network connection and never inherits
the OpenAI-compatible client. It only turns the public facts the user wrote in
``manual_providers`` into :class:`ModelInfo` objects, tags them ``tier=2`` and
``source=manual`` (shown as "手动，未核实") and drops entries whose date has
passed. Availability probing for these platforms happens **only** through the
dsh plugin, routed through the user's own dsh provider plugin, so their login
never reaches freemodel-sync.

The pure :func:`manual_probe_allowed` helper mirrors the plugin's decision
logic and is exercised by the shared conformance cases.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Iterable, List, Mapping, Optional, Tuple

from ..models import Capabilities, ModelInfo, Quota, TestResult
from .base import Provider

#: shown next to every manually registered model (never "verified")
MANUAL_LABEL = "手动，未核实"


def _get(entry: Any, *names: str, default: Any = None) -> Any:
    if isinstance(entry, Mapping):
        for name in names:
            if name in entry:
                return entry[name]
        return default
    for name in names:
        if hasattr(entry, name):
            return getattr(entry, name)
    return default


def entry_expired(expires_at: Optional[str], today: Optional[date] = None) -> bool:
    """True when *expires_at* (``YYYY-MM-DD``) is before *today*."""

    if not expires_at:
        return False
    try:
        expiry = date.fromisoformat(str(expires_at)[:10])
    except ValueError:
        return False
    return expiry < (today or date.today())


def _record_date(record: Mapping[str, Any]) -> Optional[date]:
    tested_at = record.get("tested_at")
    if not isinstance(tested_at, (int, float)):
        return None
    return datetime.fromtimestamp(float(tested_at), timezone.utc).date()


def manual_probe_allowed(
    entry: Any,
    probes: Iterable[Mapping[str, Any]],
    *,
    enabled: bool,
    now: Optional[datetime] = None,
) -> Tuple[bool, Optional[str]]:
    """Decide whether the dsh plugin may probe *entry* now.

    Rules, in order: global switch, per-entry opt-in, expiry, an account
    failure on the same platform today (stops every model), and one probe per
    model per UTC day. A ``capacity`` result is recorded but does not stop the
    platform. Returns ``(allowed, reason)`` where reason is one of
    ``disabled``/``probe-off``/``expired``/``platform-stopped``/``daily-limit``.
    """

    if not enabled:
        return False, "disabled"
    if _get(entry, "probe", default=False) is not True:
        return False, "probe-off"
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    expires_at = _get(entry, "expiresAt", "expires_at")
    if entry_expired(expires_at, today):
        return False, "expired"
    provider = str(_get(entry, "dshProvider", "dsh_provider", default=""))
    model = str(_get(entry, "model", default=""))
    for record in probes:
        if not isinstance(record, Mapping) or _record_date(record) != today:
            continue
        if str(record.get("provider", "")) != provider:
            continue
        if record.get("failure_kind") == "account":
            return False, "platform-stopped"
        if str(record.get("model", "")) == model:
            return False, "daily-limit"
    return True, None


class ManualProvider(Provider):
    """A tier-2 provider built from public registration data only."""

    tier = 2
    #: no endpoint is ever contacted by this class
    base_url = ""
    api_key_env = ""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        name: str,
        display_name: str = "",
        auth: str = "oauth_manual",
        dsh_provider: str = "",
        dsh_plugin: str = "",
        models: Iterable[Any] = (),
        today: Optional[date] = None,
    ) -> None:
        super().__init__(api_key=api_key)
        self.name = name
        self.display_name = display_name or name
        self.auth_kind = auth
        self.dsh_provider = dsh_provider or name
        self.dsh_plugin = dsh_plugin
        self.models = list(models)
        self.today = today

    @classmethod
    def from_config(cls, entry: Any, *, today: Optional[date] = None) -> ManualProvider:
        return cls(
            name=str(_get(entry, "name")),
            display_name=str(_get(entry, "display_name", default="")),
            auth=str(_get(entry, "auth", default="oauth_manual")),
            dsh_provider=str(_get(entry, "dsh_provider", default="")),
            dsh_plugin=str(_get(entry, "dsh_plugin", default="")),
            models=list(_get(entry, "models", default=()) or ()),
            today=today,
        )

    def discover(self) -> List[ModelInfo]:
        """Return registered, non-expired models; no request is made."""

        found: List[ModelInfo] = []
        for model in self.models:
            model_id = str(_get(model, "id", default=""))
            if not model_id or entry_expired(_get(model, "expires_at", "expiresAt"), self.today):
                continue
            name = str(_get(model, "name", default="") or model_id)
            tools = _get(model, "tools")
            quota = _get(model, "quota")
            if isinstance(quota, Mapping):
                quota = Quota.from_dict(quota)
            if not isinstance(quota, Quota):
                quota = None
            if quota is not None:
                quota.source = "manual"
                if quota.expires_at is None:
                    quota.expires_at = _get(model, "expires_at", "expiresAt")
            expires_at = _get(model, "expires_at", "expiresAt")
            expiration = date.fromisoformat(str(expires_at)[:10]) if expires_at else None
            capabilities = Capabilities(tools=tools, source="manual")
            found.append(
                ModelInfo(
                    provider=self.name,
                    id=model_id,
                    name=f"{name} ({MANUAL_LABEL})",
                    capabilities=capabilities,
                    quota=quota,
                    tier=2,
                    expiration_date=expiration,
                    raw={
                        "manual": True,
                        "display_name": self.display_name,
                        "dsh_provider": self.dsh_provider,
                        "dsh_plugin": self.dsh_plugin,
                    },
                )
            )
        return found

    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        """Refuse to probe: availability checks belong to the dsh plugin.

        This method deliberately sends nothing. It returns a model-level
        failure so callers never mistake an unverified registration for a
        working free model.
        """

        return TestResult(
            key=model.key,
            ok=False,
            error="manual registration: availability is probed only through dsh; freemodel-sync sent no request",
            failure_kind="model",
            tested_at=time.time(),
        )

    def capabilities_for(self, model: ModelInfo) -> Capabilities:
        return model.capabilities

    def quota(self) -> Optional[Quota]:
        return None
