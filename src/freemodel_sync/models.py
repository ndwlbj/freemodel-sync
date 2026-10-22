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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TestResult:
        fields = {k: data.get(k) for k in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        fields["ok"] = bool(fields.get("ok"))
        fields["tested_at"] = float(fields.get("tested_at") or 0.0)
        fields["cached"] = bool(fields.get("cached"))
        return cls(**fields)  # type: ignore[arg-type]


@dataclass
class QuotaInfo:
    """Provider-side quota / usage information (best effort)."""

    is_free_tier: Optional[bool] = None
    daily_free_limit: Optional[int] = None  # e.g. 50 or 1000 requests/day on OpenRouter
    usage: Optional[float] = None
    limit_remaining: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_free_tier": self.is_free_tier,
            "daily_free_limit": self.daily_free_limit,
            "usage": self.usage,
            "limit_remaining": self.limit_remaining,
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
