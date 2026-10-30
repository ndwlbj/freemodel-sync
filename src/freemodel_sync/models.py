"""Core data types shared by providers, the tester, the ranker and adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Literal, Mapping, Optional

#: How a provider authenticates. ``oauth_manual`` is for tier-2 registrations
#: only: the login belongs to the third-party dsh plugin, we never hold it.
AuthKind = Literal["none", "api_key", "pat", "oauth_manual"]

#: values shared with ``spec/providers.json`` (``capabilities.sources``)
CAPABILITY_SOURCES = ("catalog", "config", "probe", "manual", "unknown")
#: values shared with ``spec/providers.json`` (``quota.units``)
QUOTA_UNITS = ("requests", "tokens", "credits", "unknown")
#: values shared with ``spec/providers.json`` (``quota.periods``)
QUOTA_PERIODS = ("rolling_5h", "week", "day", "total", "beta", "unknown")
#: length of one window, for the periods that have a fixed one
QUOTA_PERIOD_SECONDS = {"rolling_5h": 5 * 3600, "week": 7 * 24 * 3600, "day": 24 * 3600}

_QUOTA_PERIOD_ALIASES = {
    "5h": "rolling_5h",
    "5_h": "rolling_5h",
    "5-hour": "rolling_5h",
    "5_hour": "rolling_5h",
    "rolling-5h": "rolling_5h",
    "rolling5h": "rolling_5h",
    "five_hour": "rolling_5h",
    "weekly": "week",
    "per_week": "week",
    "7d": "week",
    "daily": "day",
    "per_day": "day",
    "once": "total",
    "one_time": "total",
    "one-time": "total",
    "public_beta": "beta",
    "trial": "beta",
    "": "unknown",
}
_QUOTA_UNIT_ALIASES = {
    "request": "requests",
    "req": "requests",
    "token": "tokens",
    "credit": "credits",
    "": "unknown",
}


def _optional_bool(value: Any) -> Optional[bool]:
    """Read a capability flag; anything missing or unrecognised is unknown (``None``)."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "yes", "1", "supported"):
            return True
        if text in ("false", "no", "0", "unsupported"):
            return False
        # "", "unknown", "?", "n/a" and anything unexpected all mean unknown
    return None


def _json_number(value: Optional[float]) -> Any:
    """Keep whole numbers as ints in JSON while the in-memory type stays float."""

    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def _choice(value: Any, choices: tuple[str, ...], aliases: Mapping[str, str], default: str = "unknown") -> str:
    if not isinstance(value, str):
        return default
    text = value.strip().lower()
    text = aliases.get(text, text)
    return text if text in choices else default


@dataclass
class Capabilities:
    """What a model can do; ``None`` means the catalogue does not say (unknown).

    ``source`` says where the flags came from, matching ``capabilities.sources``
    in ``spec/providers.json``: a catalogue field, local config, a probe, a
    manual registry entry, or nowhere (unknown).
    """

    tools: Optional[bool] = None
    vision: Optional[bool] = None
    reasoning: Optional[bool] = None
    source: str = "catalog"

    def __post_init__(self) -> None:
        self.tools = _optional_bool(self.tools)
        self.vision = _optional_bool(self.vision)
        self.reasoning = _optional_bool(self.reasoning)
        self.source = _choice(self.source, CAPABILITY_SOURCES, {}, default="unknown")
        if self.tools is None and self.vision is None and self.reasoning is None:
            self.source = "unknown"

    @property
    def known(self) -> bool:
        """True when at least one capability is known."""

        return any(value is not None for value in (self.tools, self.vision, self.reasoning))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tools": self.tools,
            "vision": self.vision,
            "reasoning": self.reasoning,
            "source": self.source,
        }

    @classmethod
    def from_dict(
        cls,
        data: Any = None,
        *,
        supports_tools: Optional[bool] = None,
    ) -> Capabilities:
        """Read old or new data; missing/unknown fields stay ``None``.

        Old model documents only had ``supports_tools``. It is used as the
        ``tools`` flag when the new ``capabilities`` object is absent, so old
        caches keep their tool information instead of losing it.
        """

        if isinstance(data, cls):
            return data
        raw: Mapping[str, Any] = data if isinstance(data, Mapping) else {}
        tools_missing = "tools" not in raw
        tools = _optional_bool(raw.get("tools"))
        if tools is None and tools_missing:
            tools = _optional_bool(supports_tools)
        source = raw.get("source")
        if source is None:
            source = "catalog" if (tools is not None or raw) else "unknown"
        result = cls(
            tools=tools,
            vision=_optional_bool(raw.get("vision")),
            reasoning=_optional_bool(raw.get("reasoning")),
            source=str(source),
        )
        return result


@dataclass
class Quota:
    """A provider quota, independent of unit and reset window.

    The periods cover what the supported providers actually use:

    * ``rolling_5h``: a five-hour rolling window (SenseNova's free pool);
    * ``week``: a weekly window (SenseNova);
    * ``day``: a daily reset (OpenRouter and Groq request limits);
    * ``total``: a one-off allowance that never resets (Bailian's new-user
      tokens);
    * ``beta``: no numeric limit during a public beta;
    * ``unknown``: the provider does not report one.

    Every number is optional. ``remaining_today`` is deliberately conservative
    and returns ``None`` (shown as unknown) when the value cannot be computed.
    Manual values are shown but never reduced by local probe counts.
    """

    unit: str = "unknown"
    period: str = "unknown"
    limit: Optional[float] = None
    used: Optional[float] = None
    remaining: Optional[float] = None
    #: ISO-8601 timestamp with a timezone, when the provider gives one
    resets_at: Optional[str] = None
    #: ISO-8601 timestamp after which the free allowance ends
    expires_at: Optional[str] = None
    source: str = "none"
    scope: str = "account"
    #: probes sent after the counters were read (set by the caller)
    probes_since_read: int = 0

    def __post_init__(self) -> None:
        self.unit = _choice(self.unit, QUOTA_UNITS, _QUOTA_UNIT_ALIASES)
        self.period = _choice(self.period, QUOTA_PERIODS, _QUOTA_PERIOD_ALIASES)
        for name in ("limit", "used", "remaining"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                setattr(self, name, float(value))
            except (TypeError, ValueError):
                setattr(self, name, None)
        if self.source not in ("api", "headers", "manual", "none"):
            self.source = "none"
        if self.scope not in ("account", "model"):
            self.scope = "account"
        self.probes_since_read = max(0, int(self.probes_since_read or 0))

    @property
    def window_seconds(self) -> Optional[int]:
        """Length of the quota window, when it has a fixed one."""

        return QUOTA_PERIOD_SECONDS.get(self.period)

    @property
    def remaining_window(self) -> Optional[float]:
        """Remaining allowance for a day/week/rolling window, else ``None``.

        A snapshot is read before a probing round. For provider-reported values
        the local probe count is subtracted (conservative); a manual value is
        shown as entered, because the user's number is not tied to this run.
        """

        if self.period not in ("rolling_5h", "week", "day"):
            return None
        base = self._base_remaining()
        if base is None or self.source == "manual":
            return base
        return max(0.0, base - self.probes_since_read)

    @property
    def remaining_today(self) -> Optional[float]:
        """Remaining allowance for a daily quota (``None`` for other periods)."""

        return self.remaining_window if self.period == "day" else None

    @property
    def remaining_total(self) -> Optional[float]:
        """Remaining one-off allowance; ``None`` unless ``period`` is ``total``."""

        return self._base_remaining() if self.period == "total" else None

    @property
    def remaining_estimate(self) -> Optional[float]:
        """Backward-compatible alias of :attr:`remaining_today`."""

        return self.remaining_today

    @property
    def is_exhausted(self) -> bool:
        """True only when the quota is known to be used up."""

        remaining = self.remaining_window if self.period in ("rolling_5h", "week", "day") else self.remaining_total
        if remaining is not None:
            return remaining <= 0
        return self.limit is not None and self.used is not None and self.used >= self.limit

    # -- legacy daily-request view (used by the probing budget) ------------
    @property
    def daily_free_limit(self) -> Optional[float]:
        return self.limit if self.unit == "requests" and self.period == "day" else None

    @property
    def daily_free_used(self) -> Optional[float]:
        return self.used if self.unit == "requests" and self.period == "day" else None

    @property
    def daily_free_remaining(self) -> Optional[float]:
        return self.remaining if self.unit == "requests" and self.period == "day" else None

    def _base_remaining(self) -> Optional[float]:
        if self.remaining is not None:
            return self.remaining
        if self.limit is None:
            return None
        return max(0.0, self.limit - (self.used or 0.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit": self.unit,
            "period": self.period,
            "limit": _json_number(self.limit),
            "used": _json_number(self.used),
            "remaining": _json_number(self.remaining),
            "resets_at": self.resets_at,
            "expires_at": self.expires_at,
            "source": self.source,
            "scope": self.scope,
            "window_seconds": self.window_seconds,
            "remaining_today": _json_number(self.remaining_today),
            "remaining_window": _json_number(self.remaining_window),
            "remaining_total": _json_number(self.remaining_total),
            "is_exhausted": self.is_exhausted,
            "probes_since_read": self.probes_since_read,
        }

    @classmethod
    def from_dict(cls, data: Any = None) -> Quota:
        """Read a quota document; missing or malformed values become unknown.

        Both the shared snake_case form and the plugin's camelCase form are
        accepted so old state files and JSON written by either side can be
        read. A plain ``QuotaInfo`` document (daily request counters only) is
        also understood.
        """

        if isinstance(data, cls):
            return data
        if isinstance(data, QuotaInfo):
            return cls.from_quota_info(data)
        raw: Mapping[str, Any] = data if isinstance(data, Mapping) else {}

        def pick(*names: str) -> Any:
            for name in names:
                if name in raw:
                    return raw[name]
            return None

        unit = pick("unit")
        period = pick("period")
        daily_keys = (
            "daily_free_limit",
            "dailyFreeLimit",
            "daily_free_used",
            "dailyFreeUsed",
            "daily_free_remaining",
            "dailyFreeRemaining",
        )
        has_daily = any(key in raw for key in daily_keys)
        if period is None and has_daily:
            unit = unit or "requests"
            period = "day"
        source = pick("source")
        if source is None and period == "day" and any(pick(key) is not None for key in daily_keys):
            source = "api"
        return cls(
            unit=unit if isinstance(unit, str) else "unknown",
            period=period if isinstance(period, str) else "unknown",
            limit=pick("limit", "daily_free_limit", "dailyFreeLimit"),
            used=pick("used", "daily_free_used", "dailyFreeUsed"),
            remaining=pick("remaining", "daily_free_remaining", "dailyFreeRemaining"),
            resets_at=pick("resets_at", "resetsAt"),
            expires_at=pick("expires_at", "expiresAt"),
            source=source if isinstance(source, str) else "none",
            scope=pick("scope") if isinstance(pick("scope"), str) else "account",
            probes_since_read=int(pick("probes_since_read", "probesSinceRead") or 0),
        )

    @classmethod
    def from_quota_info(cls, info: QuotaInfo) -> Quota:
        """Convert the legacy daily request counters to the generic quota."""

        return cls(
            unit="requests",
            period="day",
            limit=info.daily_free_limit,
            used=info.daily_free_used,
            remaining=info.daily_free_remaining,
            source="api"
            if any(
                value is not None for value in (info.daily_free_limit, info.daily_free_used, info.daily_free_remaining)
            )
            else "none",
            scope="account",
            probes_since_read=info.probes_since_read,
        )


@dataclass
class ModelInfo:
    """A free model discovered from a provider catalogue."""

    provider: str
    id: str
    name: str = ""
    context_length: int = 0
    #: Legacy field kept for old callers and JSON; derived from ``capabilities.tools``.
    supports_tools: bool = False
    expiration_date: Optional[date] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    capabilities: Capabilities = field(default_factory=Capabilities)
    #: Model-level quota (Bailian's per-model token allowance); account quotas live on the provider.
    quota: Optional[Quota] = None
    tier: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.capabilities, Mapping):
            self.capabilities = Capabilities.from_dict(self.capabilities)
        if not isinstance(self.capabilities, Capabilities):
            self.capabilities = Capabilities.from_dict(None)
        if self.capabilities.tools is None and self.supports_tools:
            self.capabilities.tools = True
        if self.capabilities.tools is not None:
            self.supports_tools = self.capabilities.tools is True
        if isinstance(self.quota, Mapping):
            self.quota = Quota.from_dict(self.quota)
        if not isinstance(self.quota, Quota):
            self.quota = None
        try:
            self.tier = int(self.tier)
        except (TypeError, ValueError):
            self.tier = 1

    @property
    def key(self) -> str:
        """Stable unique key, ``"<provider>|<model id>"``."""
        return f"{self.provider}|{self.id}"

    def days_until_expiry(self, today: Optional[date] = None) -> Optional[int]:
        if self.expiration_date is None:
            return None
        today = today or date.today()
        return (self.expiration_date - today).days

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "id": self.id,
            "name": self.name,
            "context_length": self.context_length,
            "supports_tools": self.supports_tools,
            "capabilities": self.capabilities.to_dict(),
            "quota": self.quota.to_dict() if self.quota is not None else None,
            "tier": self.tier,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelInfo:
        """Rebuild a model from old or new JSON.

        Missing ``capabilities`` and ``quota`` (documents written before
        ``schema_version: 2``) are read as unknown/absent rather than an error.
        """

        raw_provider = data.get("provider")
        raw_id = data.get("id")
        if not isinstance(raw_provider, str) or not isinstance(raw_id, str):
            raise ValueError("model document needs string 'provider' and 'id'")
        expiration = data.get("expiration_date")
        expiration_date: Optional[date] = None
        if isinstance(expiration, str) and expiration:
            try:
                expiration_date = date.fromisoformat(expiration[:10])
            except ValueError:
                expiration_date = None
        supports_tools = data.get("supports_tools")
        capabilities = Capabilities.from_dict(
            data.get("capabilities"),
            supports_tools=supports_tools if isinstance(supports_tools, bool) else None,
        )
        return cls(
            provider=raw_provider,
            id=raw_id,
            name=str(data.get("name") or ""),
            context_length=int(data.get("context_length") or 0),
            supports_tools=supports_tools is True,
            expiration_date=expiration_date,
            capabilities=capabilities,
            quota=Quota.from_dict(data.get("quota")) if data.get("quota") is not None else None,
            tier=int(data.get("tier") or 1),
        )


@dataclass
class TestResult:
    """Outcome of one tiny probe request against a model."""

    __test__ = False  # keep pytest from collecting this class

    key: str
    ok: bool
    ttft_ms: Optional[float] = None
    total_ms: Optional[float] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    tested_at: float = 0.0  # unix timestamp
    cached: bool = False
    #: ``"model"`` when the failure is specific to this model, ``"transient"``
    #: for a model-level failure worth retrying soon (upstream 429, 5xx,
    #: timeout), ``"capacity"`` when the upstream is queued / has no capacity
    #: (retried just as soon as transient, but counted separately), ``"quota"``
    #: when the free allowance is exhausted for the day (the channel stops
    #: until the next UTC day), ``"account"`` when the failure says nothing
    #: about the model (bad/missing key, no credits, platform rate limit).
    #: Account and quota failures are never cached as model results;
    #: ``None`` when ``ok``.
    failure_kind: Optional[str] = None
    #: consecutive ``capacity`` results for this model (set by ``ResultCache``)
    capacity_streak: int = 0
    #: seconds the provider asked us to wait (``Retry-After``/``X-RateLimit-Reset``)
    retry_after_s: Optional[float] = None
    #: remaining requests reported by ``X-RateLimit-Remaining``, if any
    rate_limit_remaining: Optional[int] = None

    @property
    def is_account_error(self) -> bool:
        return not self.ok and self.failure_kind == "account"

    @property
    def is_quota_error(self) -> bool:
        """True for a daily/one-off quota exhaustion; the channel stops for the day."""

        return not self.ok and self.failure_kind == "quota"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestResult:
        """Rebuild a cached result.

        Caches written before ``failure_kind`` existed have no kind for their
        failures. Those are read as ``"model"`` on purpose: the conservative
        choice blocks the model for ``cache_ttl_hours`` instead of retrying it
        after ``transient_ttl_minutes``, so an old transient failure is retried
        a little later than necessary rather than a broken model being probed
        again too early.
        """

        fields = {k: data.get(k) for k in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        fields["ok"] = bool(fields.get("ok"))
        fields["tested_at"] = float(fields.get("tested_at") or 0.0)
        fields["cached"] = bool(fields.get("cached"))
        try:
            fields["capacity_streak"] = max(0, int(fields.get("capacity_streak") or 0))
        except (TypeError, ValueError):
            fields["capacity_streak"] = 0
        if fields.get("failure_kind") is None and not fields["ok"]:
            fields["failure_kind"] = "model"
        return cls(**fields)  # type: ignore[arg-type]


#: shown next to provider-reported quota counters (see :class:`QuotaInfo`)
QUOTA_LAG_NOTE = (
    "read once before probing, so this run's probes are not included; "
    "the provider's counter can also lag behind recent requests"
)


@dataclass
class QuotaInfo:
    """Provider-side quota / usage information (best effort).

    The counters are a snapshot taken when ``/key`` (or the provider's
    equivalent) was read, which is *before* a probing round; requests sent
    afterwards are counted in :attr:`probes_since_read`.  OpenRouter's
    ``free_model_daily_requests.used`` has also been seen to trail requests
    that were already sent, so treat the numbers as lower bounds on usage.
    """

    is_free_tier: Optional[bool] = None
    #: free-model requests allowed per (UTC) day, as reported by the provider
    daily_free_limit: Optional[int] = None
    #: free-model requests used / remaining in the current UTC day, as reported
    daily_free_used: Optional[int] = None
    daily_free_remaining: Optional[int] = None
    usage: Optional[float] = None
    limit_remaining: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    #: probe requests sent after the counters were read (set by the caller)
    probes_since_read: int = 0

    @property
    def remaining_estimate(self) -> Optional[int]:
        """``daily_free_remaining`` minus the probes sent since it was read."""

        if self.daily_free_remaining is None:
            return None
        return max(0, self.daily_free_remaining - max(0, int(self.probes_since_read)))

    def to_quota(self) -> Quota:
        """Convert to the generic :class:`Quota` (daily request window)."""

        return Quota.from_quota_info(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_free_tier": self.is_free_tier,
            "daily_free_limit": self.daily_free_limit,
            "daily_free_used": self.daily_free_used,
            "daily_free_remaining": self.daily_free_remaining,
            "usage": self.usage,
            "limit_remaining": self.limit_remaining,
            "probes_since_read": self.probes_since_read,
            "remaining_estimate": self.remaining_estimate,
            "note": QUOTA_LAG_NOTE,
        }


@dataclass
class RankedModel:
    model: ModelInfo
    score: float
    test: Optional[TestResult] = None
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = self.model.to_dict()
        d["key"] = self.model.key
        d["score"] = round(self.score, 4)
        d["test"] = self.test.to_dict() if self.test else None
        d["reasons"] = list(self.reasons)
        return d


@dataclass
class Selection:
    """What gets written into tool configs: one primary plus ordered fallbacks."""

    primary: RankedModel
    fallbacks: List[RankedModel] = field(default_factory=list)

    @property
    def provider(self) -> str:
        return self.primary.model.provider

    @property
    def model_ids(self) -> List[str]:
        return [self.primary.model.id] + [f.model.id for f in self.fallbacks]

    @property
    def untested_fallbacks(self) -> List[str]:
        """Ids of fallbacks that were never probed (only with allow_untested)."""
        return [f.model.id for f in self.fallbacks if f.test is None]
