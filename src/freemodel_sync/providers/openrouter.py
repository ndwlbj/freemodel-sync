"""OpenRouter provider: discover free models, probe one model, report quota.

OpenRouter's catalogue endpoint is public, so :meth:`OpenRouterProvider.discover`
works without an API key.  Testing a model and reading quota require
``OPENROUTER_API_KEY`` (or an explicitly supplied ``api_key``).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..models import ModelInfo, QuotaInfo, TestResult
from .base import Provider, ProviderError, register_provider

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


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


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_free_pricing(pricing: Any) -> bool:
    """Return ``True`` when both prompt and completion prices are exactly zero."""

    if not isinstance(pricing, dict):
        return False
    prompt = _as_float(pricing.get("prompt"))
    completion = _as_float(pricing.get("completion"))
    return prompt == 0.0 and completion == 0.0


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


def _is_free_model(model: Any) -> bool:
    """Apply OpenRouter's definition of a free text model."""

    if not isinstance(model, dict):
        return False
    model_id = model.get("id")
    if not isinstance(model_id, str) or not model_id:
        return False
    if model_id == "openrouter/free" or model_id.startswith("openrouter/"):
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
class OpenRouterProvider(Provider):
    """Provider for https://openrouter.ai (OpenAI-compatible API)."""

    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    api_key_env = "OPENROUTER_API_KEY"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        **options: Any,
    ) -> None:
        super().__init__(api_key=api_key, **options)
        # Keep a caller-supplied client (useful in tests); otherwise create one
        # lazily on first use so constructing a provider has no side effects.
        self.client = client

    # -- helpers ---------------------------------------------------------
    def _get_client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=_DEFAULT_TIMEOUT)
        return self.client

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
                continue
            supported = raw.get("supported_parameters") or []
            if not isinstance(supported, list):
                supported = []
            models.append(
                ModelInfo(
                    provider=self.name,
                    id=str(raw["id"]),
                    name=str(raw.get("name") or raw["id"]),
                    context_length=_context_length(raw),
                    supports_tools="tools" in supported,
                    expiration_date=_parse_expiration_date(raw.get("expiration_date")),
                    raw=raw,
                )
            )
        return models

    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        """Send one tiny streaming chat completion and measure TTFT/latency.

        Failures are classified (see :attr:`TestResult.failure_kind`) so the
        tester can tell a broken model from an account or quota problem:

        * 401/402/403, and OpenRouter platform 429s (free-model per-minute or
          per-day caps), are ``"account"`` failures: they say nothing about the
          model, stop the round and are never cached.
        * Upstream-provider 429s (``error.metadata.provider_name`` /
          ``provider_code`` present), 408/5xx and network errors are
          ``"transient"`` model failures, cached only briefly.
        * Anything else (e.g. 400/404 "no endpoints") is a ``"model"`` failure.
        """

        if not self.api_key:
            return TestResult(
                key=model.key,
                ok=False,
                error="missing api key",
                failure_kind="account",
                tested_at=time.time(),
            )

        try:
            max_tokens = int(self.options.get("probe_max_tokens", 8))
        except (TypeError, ValueError):
            max_tokens = 8

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model.id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = self._auth_headers()

        start = time.perf_counter()
        status_code: Optional[int] = None
        ttft_ms: Optional[float] = None
        token_seen = False
        saw_finish = False
        done_after_finish = False
        error: Optional[str] = None
        failure_kind: Optional[str] = None
        retry_after_s: Optional[float] = None
        rl_remaining: Optional[int] = None

        try:
            with self._get_client().stream(
                "POST", url, headers=headers, json=payload, timeout=timeout
            ) as response:
                status_code = response.status_code
                retry_after_s, rl_remaining = _rate_limit_hints(response.headers)
                if status_code != 200:
                    try:
                        body = response.read()
                    except Exception:  # pragma: no cover - defensive
                        body = getattr(response, "text", "") or ""
                    if isinstance(body, bytes):
                        body = body.decode("utf-8", errors="replace")
                    error_obj = _error_object(body)
                    message = error_obj.get("message") if error_obj else None
                    error = (str(message) if message else str(body).strip())[:200] or f"HTTP {status_code}"
                    return TestResult(
                        key=model.key,
                        ok=False,
                        total_ms=(time.perf_counter() - start) * 1000.0,
                        error=error,
                        status_code=status_code,
                        tested_at=time.time(),
                        failure_kind=_classify(status_code, error_obj),
                        retry_after_s=retry_after_s,
                        rate_limit_remaining=rl_remaining,
                    )

                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="replace")
                    stripped = line.strip()
                    # Ignore SSE comments such as ": OPENROUTER PROCESSING".
                    if not stripped.startswith("data:"):
                        continue
                    data = stripped[len("data:") :].strip()
                    if data == "[DONE]":
                        if saw_finish:
                            done_after_finish = True
                        continue
                    try:
                        chunk = json.loads(data)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    if "error" in chunk:
                        err = chunk.get("error")
                        if isinstance(err, dict):
                            error = str(err.get("message") or err.get("code") or err)
                            code = err.get("code")
                            failure_kind = _classify(code if isinstance(code, int) else None, err)
                        else:
                            error = str(err)
                            failure_kind = "model"
                        break
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice.get("delta")
                    if isinstance(delta, dict):
                        content = delta.get("content") or delta.get("reasoning")
                        if content:
                            token_seen = True
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - start) * 1000.0
                    if choice.get("finish_reason") is not None:
                        saw_finish = True
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"
            failure_kind = "transient"

        total_ms = (time.perf_counter() - start) * 1000.0
        ok = (
            status_code == 200
            and error is None
            and (token_seen or done_after_finish)
        )
        if not ok and failure_kind is None:
            failure_kind = "model"
            if error is None:
                error = "empty response"
        return TestResult(
            key=model.key,
            ok=ok,
            ttft_ms=ttft_ms,
            total_ms=total_ms,
            error=error,
            status_code=status_code,
            tested_at=time.time(),
            failure_kind=None if ok else failure_kind,
            retry_after_s=retry_after_s,
            rate_limit_remaining=rl_remaining,
        )

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


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_object(body: str) -> Dict[str, Any]:
    """Extract the ``error`` object from an OpenRouter JSON error body."""

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return payload["error"]
    return {}


def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
    """Classify a failed probe as ``"account"``, ``"transient"`` or ``"model"``."""

    if status_code in (401, 402, 403):
        return "account"
    if status_code == 429:
        metadata = error_obj.get("metadata") if isinstance(error_obj, dict) else None
        metadata = metadata if isinstance(metadata, dict) else {}
        if metadata.get("provider_name") or metadata.get("provider_code") is not None:
            # The upstream provider of *this* model is saturated.
            return "transient"
        # OpenRouter platform limit (free-model per-minute/per-day cap).
        return "account"
    if status_code is not None and (status_code == 408 or status_code >= 500):
        return "transient"
    return "model"


def _rate_limit_hints(headers: Any) -> Tuple[Optional[float], Optional[int]]:
    """Return ``(retry_after_seconds, remaining)`` from rate-limit headers."""

    retry_after: Optional[float] = None
    remaining: Optional[int] = None
    try:
        raw_retry = headers.get("retry-after")
        raw_reset = headers.get("x-ratelimit-reset")
        raw_remaining = headers.get("x-ratelimit-remaining")
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
            if reset > 1e11:  # epoch milliseconds
                reset /= 1000.0
            if reset > 1e9:  # absolute epoch seconds
                retry_after = max(0.0, reset - time.time())
            else:  # relative seconds
                retry_after = max(0.0, reset)
        except ValueError:
            retry_after = None
    if raw_remaining:
        remaining = _as_int(raw_remaining)
    return retry_after, remaining
