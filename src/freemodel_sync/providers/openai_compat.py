"""Shared base for providers with an OpenAI-compatible chat completions API.

:class:`OpenAICompatProvider` holds what OpenRouter, Groq and later providers
have in common: a lazily created HTTP client, bearer authentication and the
streaming probe (``POST {base_url}/chat/completions`` with ``stream: true``)
that measures time to first token and classifies failures.

Subclasses implement :meth:`~freemodel_sync.providers.base.Provider.discover`
(and optionally ``quota``) and adapt the probe through hooks:

* :meth:`OpenAICompatProvider._classify` -- non-200 status -> failure kind;
* :meth:`OpenAICompatProvider._rate_limit_hints` -- response headers ->
  ``(retry_after_seconds, remaining)``;
* :meth:`OpenAICompatProvider._auth_headers` -- request headers;
* :attr:`OpenAICompatProvider.max_tokens_param` -- name of the token budget field.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

from ..models import ModelInfo, TestResult
from ..spec import classify_with, default_error_map, providers_spec
from .base import Provider

#: completion budget of a probe; some upstreams reject very small values
DEFAULT_PROBE_MAX_TOKENS = 16

_DEFAULT_TIMEOUT = 30.0

#: a probe may take at most ``timeout * _PROBE_DEADLINE_FACTOR`` seconds in total
#: before its first token; ``timeout`` itself is httpx's per-read timeout,
#: which every keep-alive comment resets
_PROBE_DEADLINE_FACTOR = 2.0

#: longest wait honoured from ``Retry-After`` / ``X-RateLimit-Reset``
_MAX_RETRY_AFTER_S = 24 * 3600.0


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    """Parse an integer, also from integral decimal strings such as ``"0.0"``."""

    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _error_object(body: str) -> Dict[str, Any]:
    """Extract the error object from an OpenAI-style or DashScope-style JSON body.

    Most providers nest it under ``error``. DashScope sometimes returns
    ``code`` / ``message`` at the top level, so those fields are used when no
    nested object exists (the classifier's dotted paths still work).
    """

    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("error"), dict):
        return payload["error"]
    top = {key: payload[key] for key in ("code", "message", "type") if key in payload}
    return top


def classify_status(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
    """Default, conservative classification of a non-200 probe response.

    401/402/403 and 429 are ``"account"`` failures (they stop probing this
    provider for the run), 408 and 5xx are ``"transient"``, anything else
    is a ``"model"`` failure. The rules are ``defaultErrorMap`` in
    ``spec/providers.json``.
    """

    return classify_with(default_error_map(), status_code, error_obj)


def classify_stream_error(
    code: Optional[int],
    error_obj: Dict[str, Any],
    classify: Callable[[Optional[int], Dict[str, Any]], str],
) -> str:
    """Classify an error that arrived inside the SSE stream, after HTTP 200.

    Platform limits (rate caps, budgets, bad keys) are enforced before the
    response starts, as a non-200 status. An error event after the stream
    began, such as a mid-stream rate limit or an upstream failure, therefore
    concerns this model and is ``"transient"`` (cached briefly, probing goes
    on). Only an explicit ``401``/``402`` code, or a ``403`` that the
    provider's pre-stream rules treat as an account error, still stops the
    round. Other ``4xx`` codes (``400``, ``404``, ...) are ``"model"``
    failures, unless the provider's pre-stream rules call that code transient
    (Groq's ``498``).

    *classify* is the provider's pre-stream classifier, used for ``403`` and
    non-standard ``4xx`` codes.
    """

    rules = providers_spec()["streamError"]
    if code in rules["accountCodes"]:
        return "account"
    if code in rules["delegateCodes"]:
        return classify(code, error_obj)
    if code is not None and 400 <= code < 500 and code not in rules["transientCodes"]:
        return "transient" if classify(code, error_obj) == "transient" else "model"
    return "transient"


def retry_after_hint(headers: Any) -> Tuple[Optional[float], Optional[int]]:
    """Default rate-limit hints: ``Retry-After`` in seconds (capped at 24 h), no remaining count."""

    try:
        raw_retry = headers.get("retry-after")
    except AttributeError:  # pragma: no cover - defensive
        return None, None
    if not raw_retry:
        return None, None
    try:
        retry_after = max(0.0, float(raw_retry))
    except ValueError:
        return None, None
    return min(retry_after, _MAX_RETRY_AFTER_S), None


class OpenAICompatProvider(Provider):
    """Base class for providers that speak the OpenAI chat completions API.

    Not registered itself: concrete subclasses set ``name``, ``base_url`` and
    ``api_key_env``, implement ``discover()`` and use ``@register_provider``.
    """

    #: request field carrying the probe's completion budget
    max_tokens_param = "max_tokens"

    # -- hooks -------------------------------------------------------------
    @staticmethod
    def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
        return classify_status(status_code, error_obj)

    @staticmethod
    def _rate_limit_hints(headers: Any) -> Tuple[Optional[float], Optional[int]]:
        return retry_after_hint(headers)

    def _classify_stream_error(self, code: Optional[int], error_obj: Dict[str, Any]) -> str:
        # Instance method so that a subclass's own ``_classify`` rules (e.g.
        # Groq's 403/498) also apply to errors that arrive inside the stream.
        return classify_stream_error(code, error_obj, classify=self._classify)

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
        self._owns_client = False

    def close(self) -> None:
        """Close the HTTP client this provider created; a caller-supplied client is left open."""

        if self._owns_client and self.client is not None:
            self.client.close()
            self.client = None
            self._owns_client = False

    # -- helpers ---------------------------------------------------------
    def _get_client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=_DEFAULT_TIMEOUT)
            self._owns_client = True
        return self.client

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # -- probe -------------------------------------------------------------
    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        """Send one tiny streaming chat completion and measure TTFT/latency.

        Failures are classified (see :attr:`TestResult.failure_kind`) so the
        tester can tell a broken model from an account or quota problem:

        * A non-200 status is classified by the provider's :meth:`_classify`
          hook (OpenRouter and Groq document their own rules there).
        * An error event inside the stream (after HTTP 200), such as a
          mid-stream rate limit, is classified by :meth:`_classify_stream_error`:
          ``"transient"`` unless it carries an explicit account code.
          ``"error": null`` (or an empty error) in a normal chunk is ignored.
        * A stream that ends with ``finish_reason: "error"`` is a transient
          failure even without an error object (``"content_filter"`` is a
          model failure); ``stop``/``length``/``tool_calls`` are normal ends.
        * A stream that sends no token within ``timeout * 2`` seconds in total
          (keep-alive comments do not count) is a transient failure.
        * Network errors are transient.
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
            max_tokens = int(self.options.get("probe_max_tokens", DEFAULT_PROBE_MAX_TOKENS))  # type: ignore[call-overload]
        except (TypeError, ValueError):
            max_tokens = DEFAULT_PROBE_MAX_TOKENS
        max_tokens = max(1, max_tokens)

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model.id,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            self.max_tokens_param: max_tokens,
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
            with self._get_client().stream("POST", url, headers=headers, json=payload, timeout=timeout) as response:
                status_code = response.status_code
                retry_after_s, rl_remaining = self._rate_limit_hints(response.headers)
                if status_code != 200:
                    try:
                        raw_body = response.read()
                    except Exception:  # noqa: BLE001 - the status code alone still classifies the failure
                        # Do not fall back to ``response.text``: on an unread
                        # streaming response it raises ResponseNotRead.
                        raw_body = b""
                    body = raw_body.decode("utf-8", errors="replace")
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
                        failure_kind=self._classify(status_code, error_obj),
                        retry_after_s=retry_after_s,
                        rate_limit_remaining=rl_remaining,
                    )

                deadline = start + timeout * _PROBE_DEADLINE_FACTOR
                for line in response.iter_lines():
                    if not token_seen and time.perf_counter() > deadline:
                        # Keep-alive comments reset httpx's per-read timeout, so a
                        # model that never answers needs its own wall-clock limit.
                        error = f"no token within {timeout * _PROBE_DEADLINE_FACTOR:g}s"
                        failure_kind = "transient"
                        break
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
                    err = chunk.get("error")
                    if err:
                        # HTTP 200 was already sent: the request was admitted, so
                        # this is about the model or its upstream, not the account.
                        # (``"error": null`` / ``{}`` in a normal chunk is not an error.)
                        if isinstance(err, dict):
                            error = str(err.get("message") or err.get("code") or err)
                            failure_kind = self._classify_stream_error(_as_int(err.get("code")), err)
                        else:
                            error = str(err)
                            failure_kind = self._classify_stream_error(None, {})
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
                    finish = choice.get("finish_reason")
                    if finish is not None:
                        saw_finish = True
                        if finish == "error":
                            # Generation failed upstream, even if some tokens came first.
                            error = "stream ended with finish_reason 'error'"
                            failure_kind = "transient"
                            break
                        if finish == "content_filter":
                            error = "stream ended with finish_reason 'content_filter'"
                            failure_kind = "model"
                            break
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"
            failure_kind = "transient"

        total_ms = (time.perf_counter() - start) * 1000.0
        ok = status_code == 200 and error is None and (token_seen or done_after_finish)
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
