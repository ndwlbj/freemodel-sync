"""Groq provider (https://groq.com, OpenAI-compatible API).

Why Groq and how "free" is decided
----------------------------------
Groq's model list (``GET /openai/v1/models``) has no prices, so freeness
cannot be read per model. Instead it is a property of the *account*: an
organization on Groq's **Free plan** (no payment method on file) cannot be
billed; every model is usable within per-model rate limits. Upgrading to the
Developer plan makes every request billable. The API cannot tell the two
apart, so this provider only runs when you confirm the plan with
``providers.groq.plan: free``. See ``docs/providers.md`` for sources.

Quota and errors
----------------
* ``x-ratelimit-remaining-requests`` / ``x-ratelimit-reset-requests`` refer to
  requests per day (RPD); probing stops when the remaining count drops to the
  reserve, and later runs wait for the reset.
* 401/403 are account problems; 429 (rate limit) is treated as an account
  problem too, conservatively: probing of Groq stops for this run and resumes
  after ``retry-after``. Other providers are unaffected.
* 498 (flex capacity), 408 and 5xx are transient; other 4xx mean the model.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..models import ModelInfo
from .base import ProviderError, register_provider
from .openrouter import OpenRouterProvider, _as_int

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}


def parse_duration(value: Any) -> Optional[float]:
    """Parse Groq reset values such as ``"2m59.56s"``, ``"7.66s"`` or ``"120ms"``."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    parts = _DURATION_RE.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text.replace(" ", ""):
        return None
    return sum(float(number) * _UNIT_SECONDS[unit] for number, unit in parts)


@register_provider
class GroqProvider(OpenRouterProvider):
    """Groq models, usable for free only on a Free-plan organization."""

    name = "groq"
    base_url = "https://api.groq.com/openai/v1"
    api_key_env = "GROQ_API_KEY"
    max_tokens_param = "max_completion_tokens"

    @staticmethod
    def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
        if status_code in (401, 403, 429):
            return "account"
        if status_code is not None and (status_code in (408, 498) or status_code >= 500):
            return "transient"
        return "model"

    @staticmethod
    def _rate_limit_hints(headers: Any) -> Tuple[Optional[float], Optional[int]]:
        try:
            raw_retry = headers.get("retry-after")
            raw_reset = headers.get("x-ratelimit-reset-requests")
            raw_remaining = headers.get("x-ratelimit-remaining-requests")
        except AttributeError:  # pragma: no cover - defensive
            return None, None
        retry_after = parse_duration(raw_retry)
        if retry_after is None:
            retry_after = parse_duration(raw_reset)
        return retry_after, _as_int(raw_remaining)

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _check_plan(self) -> None:
        plan = str(self.options.get("plan") or "").strip().lower()
        if plan != "free":
            raise ProviderError(
                "groq: set providers.groq.plan: free to confirm your Groq organization is on the "
                "Free plan (no payment method). Groq's API does not report prices or the plan, and "
                "on the Developer plan every request is billed, so nothing is listed or probed "
                "without this confirmation."
            )

    def discover(self) -> List[ModelInfo]:
        """List active Groq models (needs the API key: Groq's model list is authenticated)."""

        self._check_plan()
        if not self.api_key:
            raise ProviderError(f"groq: listing models needs {self.api_key_env} (Groq's model list requires a key)")
        try:
            response = self._get_client().get(f"{self.base_url}/models", headers=self._auth_headers())
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Groq model list failed: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Groq model list failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise ProviderError("Groq returned invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProviderError("Groq returned an unexpected models payload")

        models: List[ModelInfo] = []
        for raw in payload["data"]:
            if not isinstance(raw, dict):
                continue
            model_id = raw.get("id")
            if not isinstance(model_id, str) or not model_id or raw.get("active") is False:
                continue
            context = _as_int(raw.get("context_window")) or 0
            models.append(
                ModelInfo(
                    provider=self.name,
                    id=model_id,
                    name=model_id,
                    context_length=context,
                    # Groq's list does not say which models support tools.
                    supports_tools=False,
                    raw=raw,
                )
            )
        return models

    def quota(self) -> None:  # type: ignore[override]
        """Groq has no quota endpoint; limits come from response headers."""
        return None

    def test(self, model: ModelInfo, timeout: float = 30.0):  # type: ignore[override]
        self._check_plan()
        return super().test(model, timeout=timeout)
