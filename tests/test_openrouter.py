from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers import ProviderError, get_provider_class
from freemodel_sync.providers.openrouter import OpenRouterProvider


def provider_with(handler, api_key="test-key", **options):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterProvider(api_key=api_key, client=client, **options)


def test_registered():
    assert get_provider_class("openrouter") is OpenRouterProvider


def test_discover_filters_free_text_models(models_payload):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json=models_payload)

    models = provider_with(handler, api_key=None).discover()
    ids = [m.id for m in models]
    assert ids, "expected some free models in the fixture"
    assert all(i.endswith(":free") for i in ids)
    assert "openrouter/free" not in ids
    assert seen["auth"] is None  # discovery needs no key
    by_id = {m.id: m for m in models}
    flint = by_id["recursive/flint-v1.0:free"]
    assert flint.supports_tools is True
    assert flint.context_length == 262144
    dots = by_id["dots-studio/dots-3-note-preview:free"]
    assert dots.expiration_date == date(2026, 12, 31)


def test_discover_rejects_nonzero_price_and_non_text():
    payload = {
        "data": [
            {
                "id": "a/paid:free",
                "pricing": {"prompt": "0.000001", "completion": "0"},
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            },
            {
                "id": "a/image:free",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
            },
            {
                "id": "a/ok:free",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"modality": "text+image->text"},
                "expiration_date": "garbage",
            },
            {
                "id": "a/notfree",
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"modality": "text->text"},
            },
        ]
    }
    models = provider_with(lambda r: httpx.Response(200, json=payload)).discover()
    assert [m.id for m in models] == ["a/ok:free"]
    assert models[0].expiration_date is None


@pytest.mark.parametrize("response", [httpx.Response(500, text="boom"), httpx.Response(200, text="not json")])
def test_discover_errors(response):
    with pytest.raises(ProviderError):
        provider_with(lambda r: response).discover()


def sse(*chunks):
    body = ": OPENROUTER PROCESSING\n\n"
    for c in chunks:
        body += "data: " + (c if isinstance(c, str) else json.dumps(c)) + "\n\n"
    return body.encode()


def test_probe_success_measures_ttft():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            content=sse(
                {"choices": [{"delta": {"content": "OK"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                "[DONE]",
            ),
            headers={"content-type": "text/event-stream"},
        )

    result = provider_with(handler).test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is True
    assert result.ttft_ms is not None and result.total_ms >= result.ttft_ms
    assert captured["body"]["stream"] is True
    assert captured["body"]["max_tokens"] == 16  # review P2-9: 8 may be below upstream minimums
    assert captured["auth"] == "Bearer test-key"


def test_probe_reasoning_tokens_count():
    handler = lambda r: httpx.Response(200, content=sse({"choices": [{"delta": {"reasoning": "hm"}}]}, "[DONE]"))
    assert provider_with(handler).test(ModelInfo("openrouter", "x/y:free")).ok is True


def test_probe_stream_error_chunk():
    handler = lambda r: httpx.Response(200, content=sse({"error": {"message": "Provider returned error"}}))
    result = provider_with(handler).test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is False
    assert "Provider returned error" in result.error


def test_probe_http_429():
    handler = lambda r: httpx.Response(429, text="rate limited" * 50)
    result = provider_with(handler).test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is False and result.status_code == 429
    assert len(result.error) <= 200


def test_probe_transport_error():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    result = provider_with(handler).test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is False and "ConnectError" in result.error


def test_probe_without_key_makes_no_request():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    result = provider_with(handler, api_key=None).test(ModelInfo("openrouter", "x/y:free"))
    assert result.ok is False and result.error == "missing api key"


@pytest.mark.parametrize("free_tier", [True, False, None])
def test_quota_uses_free_model_daily_requests(free_tier):
    data = {
        "label": "k",
        "usage": 0.5,
        "limit": None,
        "limit_remaining": None,
        "free_model_daily_requests": {"used": 48, "limit": 50, "remaining": 2},
    }
    if free_tier is not None:
        data["is_free_tier"] = free_tier
    handler = lambda r: httpx.Response(200, json={"data": data})
    q = provider_with(handler).quota()
    # the tier comes from free_model_daily_requests, never from is_free_tier
    assert (q.daily_free_limit, q.daily_free_used, q.daily_free_remaining) == (50, 48, 2)
    assert q.usage == 0.5


def test_quota_without_free_model_daily_requests_reports_unknown():
    handler = lambda r: httpx.Response(200, json={"data": {"is_free_tier": False, "usage": 0}})
    q = provider_with(handler).quota()
    assert q.daily_free_limit is None and q.daily_free_remaining is None


def test_quota_without_key_or_on_error():
    assert provider_with(lambda r: httpx.Response(200, json={}), api_key=None).quota() is None
    assert provider_with(lambda r: httpx.Response(401, json={})).quota() is None


@pytest.mark.parametrize("option, expected", [(32, 32), ("24", 24), ("bad", 16), (0, 1)])
def test_probe_max_tokens_is_configurable(option, expected):
    """Review P2-9: providers.openrouter.probe_max_tokens."""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=sse({"choices": [{"delta": {"content": "OK"}}]}, "[DONE]"),
            headers={"content-type": "text/event-stream"},
        )

    provider_with(handler, probe_max_tokens=option).test(ModelInfo("openrouter", "x/y:free"))
    assert captured["body"]["max_tokens"] == expected


def test_pricing_overrides_with_prices_are_not_free(caplog):
    """Review P2-4: time-of-day / long-context overrides can make a :free model cost money."""

    def model(mid, overrides):
        pricing = {"prompt": "0", "completion": "0"}
        if overrides is not ...:
            pricing["overrides"] = overrides
        return {
            "id": mid,
            "name": mid,
            "pricing": pricing,
            "context_length": 1000,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        }

    payload = {
        "data": [
            model("a/plain:free", ...),
            model("b/zero-overrides:free", [{"utc_days": ["monday"], "prompt": "0", "completion": "0"}]),
            model("c/peak-priced:free", [{"utc_start": 100, "utc_end": 400, "prompt": "0.0000003", "completion": "0"}]),
            model("d/odd-format:free", {"prompt": "0"}),
            model("e/empty:free", []),
        ]
    }
    provider = provider_with(lambda request: httpx.Response(200, json=payload))
    with caplog.at_level("WARNING"):
        ids = [m.id for m in provider.discover()]
    assert ids == ["a/plain:free", "b/zero-overrides:free", "e/empty:free"]
    assert "c/peak-priced:free" in caplog.text and "pricing.overrides" in caplog.text


def test_openrouter_namespace_is_excluded_even_with_free_suffix():
    """C2: the old ``== "openrouter/free"`` check was redundant; any openrouter/* router id is excluded."""

    from freemodel_sync.providers.openrouter import _is_free_model

    free_pricing = {"prompt": "0", "completion": "0"}
    text = {"input_modalities": ["text"], "output_modalities": ["text"]}
    base = {"pricing": free_pricing, "architecture": text}
    assert _is_free_model({"id": "vendor/foo:free", **base}) is True
    assert _is_free_model({"id": "openrouter/foo:free", **base}) is False
    assert _is_free_model({"id": "openrouter/free", **base}) is False


class _ClosingTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closed = False

    def close(self):
        self.closed = True


def test_provider_close_closes_only_its_own_client(monkeypatch):
    """B14: a provider closes the client it created, never one the caller passed in."""

    transports = []
    real_client = httpx.Client

    def make_client(**kwargs):
        transport = _ClosingTransport(lambda request: httpx.Response(200, json={"data": []}))
        transports.append(transport)
        return real_client(transport=transport)

    monkeypatch.setattr("freemodel_sync.providers.openrouter.httpx.Client", make_client)
    with OpenRouterProvider(api_key=None) as provider:
        assert provider.discover() == []
        assert provider.client is not None
    assert transports[0].closed and provider.client is None
    provider.close()  # idempotent
    assert provider.discover() == []  # usable again: a new client is created
    provider.close()
    assert len(transports) == 2 and transports[1].closed

    own = _ClosingTransport(lambda request: httpx.Response(200, json={"data": []}))
    caller_client = real_client(transport=own)
    with OpenRouterProvider(api_key=None, client=caller_client) as provider:
        provider.discover()
    assert own.closed is False and provider.client is caller_client
    caller_client.close()


def test_base_provider_close_is_a_noop():
    from freemodel_sync.providers.base import Provider

    class Minimal(Provider):
        name = "minimal"

        def discover(self):
            return []

        def test(self, model, timeout=30.0):  # pragma: no cover - not called
            raise AssertionError

    with Minimal() as provider:
        assert provider.discover() == []
    provider.close()
