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
            {"id": "a/paid:free", "pricing": {"prompt": "0.000001", "completion": "0"},
             "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
            {"id": "a/image:free", "pricing": {"prompt": "0", "completion": "0"},
             "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]}},
            {"id": "a/ok:free", "pricing": {"prompt": "0", "completion": "0"},
             "architecture": {"modality": "text+image->text"}, "expiration_date": "garbage"},
            {"id": "a/notfree", "pricing": {"prompt": "0", "completion": "0"},
             "architecture": {"modality": "text->text"}},
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
    assert captured["body"]["max_tokens"] == 8
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


@pytest.mark.parametrize("free_tier,limit", [(True, 50), (False, 1000), (None, 50)])
def test_quota(free_tier, limit):
    data = {"label": "k", "usage": 0.5, "limit": None, "limit_remaining": None}
    if free_tier is not None:
        data["is_free_tier"] = free_tier
    handler = lambda r: httpx.Response(200, json={"data": data})
    q = provider_with(handler).quota()
    assert q.daily_free_limit == limit
    assert q.usage == 0.5


def test_quota_without_key_or_on_error():
    assert provider_with(lambda r: httpx.Response(200, json={}), api_key=None).quota() is None
    assert provider_with(lambda r: httpx.Response(401, json={})).quota() is None
