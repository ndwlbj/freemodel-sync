"""Groq provider: discovery, plan confirmation, error and quota handling (mocked HTTP)."""

import json

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers import ProviderError, get_provider_class
from freemodel_sync.providers.groq import GroqProvider, parse_duration

MODELS = {
    "object": "list",
    "data": [
        {
            "id": "llama-3.3-70b-versatile",
            "object": "model",
            "owned_by": "Meta",
            "active": True,
            "context_window": 131072,
        },
        {"id": "openai/gpt-oss-20b", "object": "model", "owned_by": "OpenAI", "active": True, "context_window": 131072},
        {"id": "old-model", "object": "model", "active": False, "context_window": 8192},
        {"id": "whisper-large-v3", "object": "model", "active": True, "context_window": 448},
    ],
}


def groq(handler, api_key="gsk-test", **options):
    options.setdefault("plan", "free")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqProvider(api_key=api_key, client=client, **options)


def sse(*chunks):
    lines = [f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks]
    return "".join(lines).encode()


def test_registered_with_own_key_env_and_base_url():
    cls = get_provider_class("groq")
    assert cls is GroqProvider
    assert cls.api_key_env == "GROQ_API_KEY"
    assert cls.base_url == "https://api.groq.com/openai/v1"


def test_discover_lists_active_models_with_auth():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["title"] = request.headers.get("x-title")
        return httpx.Response(200, json=MODELS)

    models = groq(handler).discover()
    assert [m.id for m in models] == ["llama-3.3-70b-versatile", "openai/gpt-oss-20b", "whisper-large-v3"]
    assert models[0].key == "groq|llama-3.3-70b-versatile" and models[0].context_length == 131072
    assert seen == {"url": "https://api.groq.com/openai/v1/models", "auth": "Bearer gsk-test", "title": None}


@pytest.mark.parametrize("plan", [None, "", "developer", "paid"])
def test_requires_free_plan_confirmation_and_sends_nothing(plan):
    calls = []
    provider = groq(lambda r: calls.append(r) or httpx.Response(200, json=MODELS), plan=plan)
    with pytest.raises(ProviderError, match="plan: free"):
        provider.discover()
    with pytest.raises(ProviderError, match="plan: free"):
        provider.test(ModelInfo("groq", "llama-3.3-70b-versatile"))
    assert calls == []


def test_discover_needs_key():
    calls = []
    with pytest.raises(ProviderError, match="GROQ_API_KEY"):
        groq(lambda r: calls.append(r), api_key=None).discover()
    assert calls == []


def test_discover_http_error_does_not_leak_key():
    with pytest.raises(ProviderError) as exc:
        groq(lambda r: httpx.Response(401, json={"error": {"message": "Invalid API Key"}})).discover()
    assert "401" in str(exc.value) and "gsk-test" not in str(exc.value)


def test_probe_success_uses_max_completion_tokens_and_reads_rpd_headers():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=sse({"choices": [{"delta": {"content": "OK"}}]}, "[DONE]"),
            headers={
                "content-type": "text/event-stream",
                "x-ratelimit-remaining-requests": "998",
                "x-ratelimit-reset-requests": "1m26.4s",
            },
        )

    result = groq(handler).test(ModelInfo("groq", "openai/gpt-oss-20b"))
    assert result.ok is True and result.rate_limit_remaining == 998
    assert captured["body"]["max_completion_tokens"] == 16 and "max_tokens" not in captured["body"]


@pytest.mark.parametrize(
    "status, kind",
    [
        (401, "account"),
        (403, "account"),
        (429, "account"),
        (498, "transient"),
        (500, "transient"),
        (503, "transient"),
        (400, "model"),
        (404, "model"),
        (422, "model"),
    ],
)
def test_error_classification(status, kind):
    def handler(request):
        return httpx.Response(status, json={"error": {"message": "x", "type": "t"}}, headers={"retry-after": "7"})

    result = groq(handler).test(ModelInfo("groq", "m"))
    assert result.ok is False and result.failure_kind == kind and result.status_code == status
    assert result.retry_after_s == 7.0


@pytest.mark.parametrize(
    "raw, seconds",
    [
        ("2", 2.0),
        ("7.66s", 7.66),
        ("2m59.56s", 179.56),
        ("1h2m3s", 3723.0),
        ("120ms", 0.12),
        ("", None),
        (None, None),
        ("soon", None),
    ],
)
def test_parse_duration(raw, seconds):
    value = parse_duration(raw)
    assert (value is None and seconds is None) or value == pytest.approx(seconds)


def test_quota_sends_no_request():
    calls = []
    assert groq(lambda r: calls.append(r)).quota() is None
    assert calls == []
