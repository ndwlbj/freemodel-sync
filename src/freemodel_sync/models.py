"""Core data types shared by providers, the tester, the ranker and adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class ModelInfo:
    """A free model discovered from a provider catalogue."""

    provider: str
    id: str
    name: str = ""
    context_length: int = 0
    supports_tools: bool = False
    expiration_date: Optional[date] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

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
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
        }


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
    #: timeout), ``"account"`` when the failure says nothing about the model
    #: (bad/missing key, no credits, platform rate limit). Account failures
    #: are never cached and stop the probing round. ``None`` when ``ok``.
    failure_kind: Optional[str] = None
    #: seconds the provider asked us to wait (``Retry-After``/``X-RateLimit-Reset``)
    retry_after_s: Optional[float] = None
    #: remaining requests reported by ``X-RateLimit-Remaining``, if any
    rate_limit_remaining: Optional[int] = None

    @property
    def is_account_error(self) -> bool:
        return not self.ok and self.failure_kind == "account"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestResult:
        fields = {k: data.get(k) for k in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        fields["ok"] = bool(fields.get("ok"))
        fields["tested_at"] = float(fields.get("tested_at") or 0.0)
        fields["cached"] = bool(fields.get("cached"))
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
