"""Probe classification edge cases (review items A1, A2, A6, B1-B5, C7)."""

from __future__ import annotations

import json
import logging
import time

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers.groq import GroqProvider
from freemodel_sync.providers.openrouter import (
    OpenRouterProvider,
    _as_int,
    _classify,
    _classify_stream_error,
    _is_free_model,
    _is_free_pricing,
    _rate_limit_hints,
)
from freemodel_sync.tester import ResultCache, run_tests


def sse(*chunks):
    parts = []
    for chunk in chunks:
        data = chunk if isinstance(chunk, bytes) else json.dumps(chunk).encode()
        parts.append(b"data: " + data + b"\n\n")
    return b"".join(parts)


def make(cls=OpenRouterProvider, handler=None, body=b"", status=200, **options):
    if handler is None:

        def handler(request):
            return httpx.Response(status, headers={"content-type": "text/event-stream"}, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return cls(api_key="test-key", client=client, **options)


def probe(body, cls=OpenRouterProvider, timeout=5.0, **options):
    provider = make(cls, body=body, **options)
    return provider.test(ModelInfo(provider.name, "x/y:free"), timeout=timeout)


# -- A1: finish_reason "error" without an error object ----------------------
@pytest.mark.parametrize("with_token", [True, False])
def test_finish_reason_error_without_error_object_is_a_failure(with_token):
    first = {"choices": [{"delta": {"content": "hi" if with_token else ""}, "finish_reason": None}]}
    body = sse(first, {"choices": [{"delta": {}, "finish_reason": "error"}]}, b"[DONE]")
    result = probe(body)
    assert result.ok is False
    assert result.failure_kind == "transient"
    assert "finish_reason 'error'" in result.error


def test_finish_reason_content_filter_is_a_model_failure():
    body = sse({"choices": [{"delta": {"content": "hi"}, "finish_reason": "content_filter"}]}, b"[DONE]")
    result = probe(body)
    assert result.ok is False and result.failure_kind == "model"


@pytest.mark.parametrize("finish", ["stop", "length", "tool_calls"])
def test_normal_finish_reasons_still_succeed(finish):
    body = sse(
        {"choices": [{"delta": {"content": "OK"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": finish}]},
        b"[DONE]",
    )
    result = probe(body)
    assert result.ok is True and result.failure_kind is None and result.error is None


# -- A2: "error": null in a normal chunk ------------------------------------
@pytest.mark.parametrize("empty", [None, "", {}])
def test_empty_error_field_in_a_healthy_stream_is_ignored(empty):
    body = sse({"error": empty, "choices": [{"delta": {"content": "hi"}}]}, b"[DONE]")
    result = probe(body)
    assert result.ok is True
    assert result.error is None and result.failure_kind is None
    assert result.ttft_ms is not None


def test_real_error_object_still_fails():
    body = sse({"error": {"code": 502, "message": "Provider returned error"}})
    result = probe(body)
    assert result.ok is False and result.failure_kind == "transient"


# -- A6: provider_name alone does not make a 403 model-specific -------------
def test_403_with_only_provider_name_is_an_account_error():
    error = {"code": 403, "message": "Forbidden", "metadata": {"provider_name": "SomeHost"}}
    assert _classify(403, error) == "account"


def test_403_with_provider_name_and_routing_metadata_is_still_model_specific():
    error = {"code": 403, "metadata": {"provider_name": "SomeHost", "model_slug": "vendor/m"}}
    assert _classify(403, error) == "model"


def test_pre_stream_403_with_only_provider_name_stops_probing(tmp_path):
    body = json.dumps({"error": {"code": 403, "message": "Forbidden", "metadata": {"provider_name": "Host"}}})
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403, content=body.encode())

    provider = make(handler=handler)
    models = [ModelInfo("openrouter", f"v/m{i}:free") for i in range(3)]
    run = run_tests(provider, models, cache=ResultCache(tmp_path / "c.json").load(), max_tests=3)
    assert len(calls) == 1
    assert run.account_error is not None
    assert dict(run) == {}


# -- B1: in-stream errors follow the provider's own rules -------------------
def test_groq_in_stream_498_is_transient_like_before_the_stream():
    result = probe(sse({"error": {"code": 498, "message": "flex capacity"}}), cls=GroqProvider, plan="free")
    assert GroqProvider._classify(498, {}) == "transient"
    assert result.ok is False and result.failure_kind == "transient"


def test_groq_in_stream_403_is_an_account_error():
    error = {"error": {"code": 403, "message": "forbidden", "metadata": {"provider_name": "groq"}}}
    result = probe(sse(error), cls=GroqProvider, plan="free")
    assert result.failure_kind == "account"


def test_openrouter_in_stream_4xx_unchanged():
    assert _classify_stream_error(400, {}) == "model"
    assert _classify_stream_error(404, {}) == "model"
    assert _classify_stream_error(429, {}) == "transient"
    assert _classify_stream_error(401, {}) == "account"
    assert _classify_stream_error(None, {}) == "transient"
    provider = OpenRouterProvider(api_key="k")
    assert provider._classify_stream_error(498, {}) == "model"


# -- B2: total deadline before the first token ------------------------------
class _KeepAlive(httpx.SyncByteStream):
    def __init__(self, pauses, delay):
        self.pauses, self.delay = pauses, delay

    def __iter__(self):
        for _ in range(self.pauses):
            time.sleep(self.delay)
            yield b": OPENROUTER PROCESSING\n\n"
        yield sse({"choices": [{"delta": {"content": "late"}}]}, b"[DONE]")


def _slow_provider(pauses, delay):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=_KeepAlive(pauses, delay))

    return make(handler=handler)


def test_keepalives_cannot_stretch_a_probe_past_its_deadline():
    provider = _slow_provider(pauses=20, delay=0.03)
    started = time.perf_counter()
    result = provider.test(ModelInfo("openrouter", "x/y:free"), timeout=0.05)
    elapsed = time.perf_counter() - started
    assert result.ok is False and result.failure_kind == "transient"
    assert "no token within" in result.error
    assert elapsed < 0.4  # 20 * 0.03 = 0.6s if the deadline were ignored


def test_a_token_within_the_deadline_succeeds():
    provider = _slow_provider(pauses=2, delay=0.01)
    result = provider.test(ModelInfo("openrouter", "x/y:free"), timeout=1.0)
    assert result.ok is True


# -- B3: every price field must be zero -------------------------------------
@pytest.mark.parametrize("key", ["request", "image", "input_cache_read", "web_search", "some_future_fee"])
def test_any_non_zero_price_field_makes_a_model_paid(key):
    assert _is_free_pricing({"prompt": "0", "completion": "0", key: "0.001"}) is False


def test_zero_or_null_extra_price_fields_stay_free():
    assert _is_free_pricing({"prompt": "0", "completion": "0", "request": "0", "image": 0, "x": None}) is True


def test_unparseable_extra_price_field_is_paid():
    assert _is_free_pricing({"prompt": "0", "completion": "0", "request": "varies"}) is False


def test_free_model_with_request_price_is_not_discovered():
    raw = {
        "id": "v/m:free",
        "pricing": {"prompt": "0", "completion": "0", "request": "0.02"},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    }
    assert _is_free_model(raw) is False


# -- B4: X-RateLimit-Reset units ---------------------------------------------
def test_reset_epoch_milliseconds():
    retry, _ = _rate_limit_hints({"x-ratelimit-reset": str(int((time.time() + 60) * 1000))})
    assert 55 <= retry <= 61


def test_reset_epoch_seconds():
    retry, _ = _rate_limit_hints({"x-ratelimit-reset": str(int(time.time() + 120))})
    assert 115 <= retry <= 121


def test_large_relative_reset_is_read_as_milliseconds(caplog):
    with caplog.at_level(logging.WARNING):
        retry, _ = _rate_limit_hints({"x-ratelimit-reset": "30000"})
    assert retry == pytest.approx(30.0)
    assert "milliseconds" in caplog.text


def test_small_relative_reset_is_seconds():
    assert _rate_limit_hints({"x-ratelimit-reset": "45"})[0] == 45.0


def test_retry_after_is_capped_at_24_hours():
    assert _rate_limit_hints({"retry-after": "999999"})[0] == 24 * 3600.0
    far = str(int((time.time() + 10 * 86400) * 1000))
    assert _rate_limit_hints({"x-ratelimit-reset": far})[0] == 24 * 3600.0


# -- B5: decimal integer strings ---------------------------------------------
@pytest.mark.parametrize(("raw", "expected"), [("0.0", 0), ("12.0", 12), ("7", 7), (" 3 ", 3), (5.0, 5)])
def test_as_int_accepts_integral_decimals(raw, expected):
    assert _as_int(raw) == expected


@pytest.mark.parametrize("raw", ["2.5", "abc", "", "nan", "inf", None, True])
def test_as_int_rejects_non_integers(raw):
    assert _as_int(raw) is None


def test_decimal_remaining_header_triggers_the_reserve_guard(tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "x-ratelimit-remaining": "0.0"},
            content=sse({"choices": [{"delta": {"content": "OK"}}]}, b"[DONE]"),
        )

    provider = make(handler=handler)
    models = [ModelInfo("openrouter", f"v/m{i}:free") for i in range(3)]
    run = run_tests(provider, models, cache=ResultCache(tmp_path / "c.json").load(), max_tests=3, reserve=0)
    assert run.probes == 1
    assert "X-RateLimit-Remaining=0" in (run.stop_reason or "")


# -- C7: unreadable error body -----------------------------------------------
class _Broken(httpx.SyncByteStream):
    def __iter__(self):
        raise httpx.ReadError("connection reset")
        yield b""  # pragma: no cover


@pytest.mark.parametrize(("status", "kind"), [(500, "transient"), (401, "account"), (404, "model")])
def test_unreadable_error_body_is_classified_by_status(status, kind):
    provider = make(handler=lambda request: httpx.Response(status, stream=_Broken()))
    result = provider.test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is False
    assert result.status_code == status
    assert result.failure_kind == kind
    assert result.error == f"HTTP {status}"
