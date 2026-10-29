"""Alibaba Cloud Bailian / DashScope provider (Beijing, OpenAI-compatible).

Why the guard and allowlist are required
----------------------------------------
The compatible API does not say which calls are free: new-user allowances are
granted per account and per model, and a paid call would spend the account's
balance. This provider therefore lists and probes nothing until **both**

* ``providers.bailian.free_quota_guard: confirmed`` confirms that the console's
  "stop when the free quota is used up" switch (``免费额度用完即停``) is on, and
* ``providers.bailian.models`` names the models to use.

Per-model allowances are entered by hand as
``{id, quota: {unit: tokens, period: total, limit: 1000000}}``. They become
``Quota(period="total", source="manual", scope="model")`` and are never used to
deduct the local probe budget. A plain string id is accepted too and yields an
unknown manual allowance.

Free models are the configured allowlist intersected with ``GET /models`` when
the catalogue can be read (it needs the key). Distilled models (their id
contains ``distill``) are marked ``tools=False``: the free distilled variants do
not support tool calling.

Errors
------
``spec/providers.json`` classifies 401 as an account failure, 403 with
``AllocationQuota.FreeTierOnly`` as a quota failure (the channel stops for the
rest of the UTC day), other 403s as model failures, queue / no-capacity codes
as ``capacity``, and 408/429/5xx as transient.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx

from ..models import Capabilities, ModelInfo, Quota, TestResult
from ..spec import classify_with, provider_spec
from .base import ProviderError, register_provider
from .openai_compat import OpenAICompatProvider, _as_int

logger = logging.getLogger(__name__)

_SPEC = provider_spec("bailian")
_GUARD_VALUE = str(_SPEC["freeRule"]["guardValue"])


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.replace(",", " ").split() if part]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _limit_of(entry: Mapping[str, Any]) -> Optional[float]:
    """Read a hand-written token limit from ``quota.limit`` / ``quota_tokens``."""

    raw = entry.get("quota")
    value: Any = None
    if isinstance(raw, Mapping):
        value = raw.get("limit")
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = raw
    if value is None:
        value = entry.get("quota_tokens")
    if value is None:
        return None
    try:
        limit = float(value)
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _manual_quota(limit: Optional[float]) -> Quota:
    """A model allowance entered by the user: total tokens, manual, unverified."""

    if limit is None:
        return Quota(unit="unknown", period="total", source="manual", scope="model")
    return Quota(unit="tokens", period="total", limit=limit, source="manual", scope="model")


@register_provider
class BailianProvider(OpenAICompatProvider):
    """Bailian models from a confirmed free-quota guard and an explicit allowlist."""

    name = "bailian"
    base_url = _SPEC["baseURL"]
    api_key_env = _SPEC["apiKeyEnv"]
    max_tokens_param = _SPEC["probe"]["maxTokensParam"]
    auth_kind = _SPEC["authKind"]
    tier = _SPEC["tier"]

    @staticmethod
    def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
        return classify_with(_SPEC["errorMap"], status_code, error_obj)

    def _guard_confirmed(self) -> bool:
        return _text(self.options.get("free_quota_guard")) == _GUARD_VALUE

    def _configured_models(self) -> List[Tuple[str, Optional[float]]]:
        """The allowlist in configured order, with optional manual token limits."""

        raw = self.options.get("models")
        if raw is None or isinstance(raw, str):
            entries: List[Any] = _strings(raw)
        elif isinstance(raw, Iterable):
            entries = list(raw)
        else:
            entries = []
        models: List[Tuple[str, Optional[float]]] = []
        seen: set[str] = set()
        for entry in entries:
            if isinstance(entry, str):
                model_id, limit = entry.strip(), None
            elif isinstance(entry, Mapping):
                model_id = str(entry.get("id") or "").strip()
                limit = _limit_of(entry)
            else:
                continue
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            models.append((model_id, limit))
        return models

    def _not_ready_reason(self) -> Optional[str]:
        if not self._guard_confirmed():
            return (
                "providers.bailian.free_quota_guard is not confirmed; confirm that the console's "
                "'stop when the free quota is used up' switch is on before listing or probing Bailian"
            )
        if not self._configured_models():
            return "providers.bailian.models is empty; list the models whose free allowance you want to use"
        return None

    def _catalog(self) -> Optional[Dict[str, Dict[str, Any]]]:
        try:
            response = self._get_client().get(f"{self.base_url}/models", headers=self._auth_headers())
            if response.status_code != 200:
                logger.warning(
                    "Bailian model list failed: HTTP %s; using the configured allowlist",
                    response.status_code,
                )
                return None
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Bailian model list failed (%s); using the configured allowlist", type(exc).__name__)
            return None
        except ValueError:
            logger.warning("Bailian returned invalid JSON; using the configured allowlist")
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            logger.warning("Bailian returned an unexpected models payload; using the configured allowlist")
            return None
        catalog: Dict[str, Dict[str, Any]] = {}
        for raw in payload["data"]:
            if isinstance(raw, dict):
                model_id = raw.get("id")
                if isinstance(model_id, str) and model_id:
                    catalog[model_id] = raw
        return catalog

    def _model(self, raw: Optional[Dict[str, Any]], fallback_id: str, limit: Optional[float]) -> ModelInfo:
        data: Dict[str, Any] = raw or {}
        model_id = str(data.get("id") or fallback_id)
        capabilities = Capabilities(source="unknown")
        if "distill" in model_id.lower():
            capabilities = Capabilities(tools=False, source="config")
        context = _as_int(data.get("context_length")) or _as_int(data.get("context_window")) or 0
        return ModelInfo(
            provider=self.name,
            id=model_id,
            name=str(data.get("name") or model_id),
            context_length=context,
            supports_tools=capabilities.tools is True,
            capabilities=capabilities,
            quota=_manual_quota(limit),
            raw=data,
            tier=self.tier,
        )

    def discover(self) -> List[ModelInfo]:
        reason = self._not_ready_reason()
        if reason is not None:
            logger.warning("Bailian: %s; nothing will be listed or probed", reason)
            return []
        if not self.api_key:
            raise ProviderError(f"bailian: listing models needs {self.api_key_env} (the model list requires a key)")

        configured = self._configured_models()
        catalog = self._catalog()
        if catalog is None:
            return [self._model(None, model_id, limit) for model_id, limit in configured]
        return [
            self._model(catalog[model_id], model_id, limit) for model_id, limit in configured if model_id in catalog
        ]

    def capabilities_for(self, model: ModelInfo) -> Capabilities:
        if "distill" in model.id.lower():
            return Capabilities(tools=False, source="config")
        return Capabilities(source="unknown")

    def quota(self) -> None:
        """Bailian allowances are per model, hand-entered; there is no account quota."""

        return None

    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        reason = self._not_ready_reason()
        if reason is not None:
            logger.warning("Bailian: %s; no request was sent", reason)
            return TestResult(
                key=model.key,
                ok=False,
                error=reason,
                failure_kind="account",
            )
        return super().test(model, timeout=timeout)
