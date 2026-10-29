"""OpenRouter provider: discover free models, probe one model, report quota.

OpenRouter's catalogue endpoint is public, so :meth:`OpenRouterProvider.discover`
works without an API key.  Testing a model and reading quota require
``OPENROUTER_API_KEY`` (or an explicitly supplied ``api_key``).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from ..models import Capabilities, ModelInfo, QuotaInfo
from ..spec import classify_with, provider_spec
from .base import ProviderError, register_provider
from .openai_compat import (
    _MAX_RETRY_AFTER_S,
    OpenAICompatProvider,
    _as_float,
    _as_int,
    classify_stream_error,
)

logger = logging.getLogger(__name__)

#: OpenRouter's entry in spec/providers.json (URLs, key variable, error rules, headers)
_SPEC = provider_spec("openrouter")
_ERROR_MAP = _SPEC["errorMap"]
_RL_HEADERS = _SPEC["rateLimitHeaders"]


def _parse_expiration_date(value: Any) -> Optional[date]:
    """Parse an OpenRouter ``expiration_date`` into a :class:`datetime.date`.

    Accepts ``"YYYY-MM-DD"`` as well as full ISO-8601 datetimes (including a
    trailing ``Z``).  Returns ``None`` when the value is missing or invalid.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _is_free_pricing(pricing: Any) -> bool:
    """Return ``True`` when every price in *pricing* is exactly zero.

    ``prompt`` and ``completion`` must be present and ``0``. Every other price
    field (``request``, ``image``, ``input_cache_read``, fields added later...)
    must be ``0`` or absent: a non-zero or unparseable value makes the model
    paid, so a new kind of charge never makes a paid model look free.
    ``overrides`` is checked separately by :func:`_priced_overrides`.
    """

    if not isinstance(pricing, dict):
        return False
    prompt = _as_float(pricing.get("prompt"))
    completion = _as_float(pricing.get("completion"))
    if prompt != 0.0 or completion != 0.0:
        return False
    for key, value in pricing.items():
        if key == "overrides" or value is None:
            continue
        if _as_float(value) != 0.0:
            return False
    return not _priced_overrides(pricing)


def _priced_overrides(pricing: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ``pricing.overrides`` entries (time-of-day or long-context prices) that cost money.

    A malformed ``overrides`` value counts as priced, so an unexpected change in
    the format never makes a paid model look free.
    """

    overrides = pricing.get("overrides")
    if overrides is None:
        return []
    if not isinstance(overrides, list):
        return [{"overrides": overrides}]
    priced = []
    for entry in overrides:
        if not isinstance(entry, dict):
            priced.append({"override": entry})
            continue
        for key in ("prompt", "completion", "request"):
            value = _as_float(entry.get(key)) if key in entry else 0.0
            if value is None or value != 0.0:
                priced.append(entry)
                break
    return priced


def _supports_text(architecture: Any) -> bool:
    """Return ``True`` for text-in/text-out (or text->text) models."""

    if not isinstance(architecture, dict):
        return False
    inputs = architecture.get("input_modalities")
    outputs = architecture.get("output_modalities")
    if isinstance(inputs, list) and isinstance(outputs, list) and inputs and outputs:
        return "text" in inputs and "text" in outputs
    modality = architecture.get("modality")
    if not isinstance(modality, str) or "->" not in modality:
        return False
    # e.g. "text+image->text": text must be among inputs and outputs.
    inputs_part, _, outputs_part = modality.partition("->")
    return "text" in inputs_part.split("+") and "text" in outputs_part.split("+")


def _supports_image(architecture: Any) -> bool:
    """Return ``True`` when the catalogue says the model accepts image input."""

    if not isinstance(architecture, dict):
        return False
    inputs = architecture.get("input_modalities")
    if isinstance(inputs, list):
        return "image" in inputs
    modality = architecture.get("modality")
    if not isinstance(modality, str) or "->" not in modality:
        return False
    return "image" in modality.partition("->")[0].split("+")


def _is_free_model(model: Any) -> bool:
    """Apply OpenRouter's definition of a free text model.

    The ``:free`` id suffix is required: OpenRouter marks its free variants this
    way and the free-request quota applies to them. A model priced at 0 without
    the suffix is deliberately not treated as free, and neither are the
    ``openrouter/*`` meta-routers. All prices must be 0 as well.
    """

    if not isinstance(model, dict):
        return False
    model_id = model.get("id")
    if not isinstance(model_id, str) or not model_id:
        return False
    if model_id.startswith("openrouter/"):  # meta-routers such as openrouter/free, not real models
        return False
    if not model_id.endswith(":free"):
        return False
    if not _is_free_pricing(model.get("pricing")):
        return False
    return _supports_text(model.get("architecture"))


def _context_length(model: Dict[str, Any]) -> int:
    top_provider = model.get("top_provider")
    top_context = top_provider.get("context_length") if isinstance(top_provider, dict) else None
    value = model.get("context_length") or top_context or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@register_provider
class OpenRouterProvider(OpenAICompatProvider):
    """Provider for https://openrouter.ai (OpenAI-compatible API).

    The streaming probe lives in :class:`.openai_compat.OpenAICompatProvider`;
    OpenRouter's own error rules are in :func:`_classify` (401/402, platform
    429s and a bare 403 are account failures; upstream 429s, 408 and 5xx are
    transient; model-specific 403s and other 4xx are model failures).
    """

    name = "openrouter"
    base_url = _SPEC["baseURL"]
    api_key_env = _SPEC["apiKeyEnv"]
    max_tokens_param = _SPEC["probe"]["maxTokensParam"]

    # OpenRouter's error and rate-limit header conventions.
    @staticmethod
    def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
        return _classify(status_code, error_obj)

    @staticmethod
    def _rate_limit_hints(headers: Any) -> Tuple[Optional[float], Optional[int]]:
        return _rate_limit_hints(headers)

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        referer = self.options.get("http_referer") or self.options.get("referer")
        if referer:
            headers["HTTP-Referer"] = str(referer)
        headers["X-Title"] = str(self.options.get("x_title") or "freemodel-sync")
        return headers

    # -- Provider API ----------------------------------------------------
    def discover(self) -> List[ModelInfo]:
        """Return the currently free text models from OpenRouter's catalogue."""

        url = f"{self.base_url}/models"
        try:
            response = self._get_client().get(url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"OpenRouter model discovery failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"OpenRouter returned invalid JSON: {exc}") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ProviderError("OpenRouter returned an unexpected models payload")

        models: List[ModelInfo] = []
        for raw in payload["data"]:
            if not _is_free_model(raw):
                pricing = raw.get("pricing") if isinstance(raw, dict) else None
                if (
                    isinstance(pricing, dict)
                    and str(raw.get("id", "")).endswith(":free")
                    and _priced_overrides(pricing)
                ):
                    logger.warning(
                        "skipping %s: pricing.overrides has non-zero prices "
                        "(it is not free at some times or context lengths)",
                        raw.get("id"),
                    )
                continue
            supported = raw.get("supported_parameters") or []
            if not isinstance(supported, list):
                supported = []
            capabilities = Capabilities(
                tools="tools" in supported,
                vision=_supports_image(raw.get("architecture")),
                reasoning="reasoning" in supported,
                source="catalog",
            )
            models.append(
                ModelInfo(
                    provider=self.name,
                    id=str(raw["id"]),
                    name=str(raw.get("name") or raw["id"]),
                    context_length=_context_length(raw),
                    supports_tools=capabilities.tools is True,
                    capabilities=capabilities,
                    expiration_date=_parse_expiration_date(raw.get("expiration_date")),
                    raw=raw,
                )
            )
        return models

    def quota(self) -> Optional[QuotaInfo]:
        """Return free-model request quota for the key, or ``None`` when unavailable.

        The source of truth is ``data.free_model_daily_requests``
        (``used`` / ``limit`` / ``remaining`` for the current UTC day). The
        tier is *not* inferred from ``is_free_tier``: OpenRouter selects it by
        all-time purchased credits, independently of that flag.
        """

        if not self.api_key:
            return None
        url = f"{self.base_url}/key"
        try:
            response = self._get_client().get(url, headers=self._auth_headers())
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("could not fetch OpenRouter quota: %s", type(exc).__name__)
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            logger.warning("OpenRouter quota response had an unexpected shape")
            return None

        is_free_tier = data.get("is_free_tier")
        if not isinstance(is_free_tier, bool):
            is_free_tier = None
        free = data.get("free_model_daily_requests")
        free = free if isinstance(free, dict) else {}
        return QuotaInfo(
            is_free_tier=is_free_tier,
            daily_free_limit=_as_int(free.get("limit")),
            daily_free_used=_as_int(free.get("used")),
            daily_free_remaining=_as_int(free.get("remaining")),
            usage=_as_float(data.get("usage")),
            limit_remaining=_as_float(data.get("limit_remaining")),
            raw=data,
        )


#: ``error.metadata`` keys that mark a 403 as specific to the requested model
#: (routing gates such as "only available on agentic harnesses", moderation
#: flags) rather than to the key or account.
def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
    """Classify a failed probe as ``"account"``, ``"transient"`` or ``"model"``.

    The rules are ``providers.openrouter.errorMap`` in ``spec/providers.json``:

    * 401/402 are account failures.
    * OpenRouter's 403 covers both account problems (budget limits,
      guardrails, key permissions; ``metadata.limit_source``) and
      model-specific refusals (a free endpoint gated to agentic harnesses,
      moderation flags). Only the latter carry routing or moderation
      metadata; a bare 403 stays an account error to be safe.
      ``metadata.provider_name`` alone is ordinary routing information, not
      a model-specific signal, so it does not make a 403 a model failure.
    * A 429 naming the upstream provider (``provider_name`` /
      ``provider_code``) means *this* model's upstream is saturated
      (transient); a bare 429 is OpenRouter's platform limit (account).
    * 408 and 5xx are transient; anything else is a model failure.
    """

    return classify_with(_ERROR_MAP, status_code, error_obj)


def _classify_stream_error(
    code: Optional[int],
    error_obj: Dict[str, Any],
    classify: Optional[Callable[[Optional[int], Dict[str, Any]], str]] = None,
) -> str:
    """Classify an error inside the SSE stream; see :func:`.openai_compat.classify_stream_error`.

    *classify* is the provider's pre-stream classifier (default: OpenRouter's
    :func:`_classify`), used for ``403`` and non-standard ``4xx`` codes.
    """

    return classify_stream_error(code, error_obj, classify=classify or _classify)


def _rate_limit_hints(headers: Any) -> Tuple[Optional[float], Optional[int]]:
    """Return ``(retry_after_seconds, remaining)`` from rate-limit headers."""

    retry_after: Optional[float] = None
    remaining: Optional[int] = None
    try:
        raw_retry = headers.get(_RL_HEADERS["retryAfter"])
        raw_reset = headers.get(_RL_HEADERS["reset"])
        raw_remaining = headers.get(_RL_HEADERS["remaining"])
    except AttributeError:  # pragma: no cover - defensive
        return None, None
    if raw_retry:
        try:
            retry_after = max(0.0, float(raw_retry))
        except ValueError:
            retry_after = None
    if retry_after is None and raw_reset:
        try:
            reset = float(raw_reset)
        except ValueError:
            reset = None
        if reset is not None:
            if reset > 1e11:  # epoch milliseconds (OpenRouter's documented format)
                retry_after = max(0.0, reset / 1000.0 - time.time())
            elif reset > 1e9:  # epoch seconds
                retry_after = max(0.0, reset - time.time())
            elif reset > 3600:
                # Not an epoch time: a relative value this large is almost
                # certainly milliseconds (30000 means 30 s, not 8 hours).
                logger.warning("X-RateLimit-Reset %r read as relative milliseconds", raw_reset)
                retry_after = reset / 1000.0
            else:  # relative seconds
                retry_after = max(0.0, reset)
    if raw_remaining:
        remaining = _as_int(raw_remaining)
    if retry_after is not None and retry_after > _MAX_RETRY_AFTER_S:
        logger.warning("rate-limit reset %.0fs away; capping the pause at 24h", retry_after)
        retry_after = _MAX_RETRY_AFTER_S
    return retry_after, remaining
