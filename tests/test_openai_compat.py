"""The shared OpenAI-compatible base class (roadmap M2: pure refactor).

The OpenRouter and Groq test modules are the acceptance tests for "no behaviour
change"; this module covers the base class's own defaults, which a provider
without special rules (e.g. a future SenseNova or Bailian provider) inherits.
"""

from __future__ import annotations

import json

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers import available_providers
from freemodel_sync.providers.groq import GroqProvider
from freemodel_sync.providers.openai_compat import (
    OpenAICompatProvider,
    classify_status,
    classify_stream_error,
    retry_after_hint,
)
from freemodel_sync.providers.openrouter import OpenRouterProvider


class Plain(OpenAICompatProvider):
    """A minimal provider that only relies on the base class's defaults."""

    name = "plain-test"
    base_url = "https://plain.invalid/v1"
    api_key_env = "PLAIN_TEST_KEY"

    def discover(self):
        return []


def make(handler):
    return Plain(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openrouter_and_groq_share_the_base_class():
    assert issubclass(OpenRouterProvider, OpenAICompatProvider)
    assert issubclass(GroqProvider, OpenAICompatProvider)
    assert not issubclass(GroqProvider, OpenRouterProvider)
    assert {"groq", "openrouter"} <= set(available_providers())


def test_default_probe_request_and_success():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        chunk = {"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]}
        body = b"data: " + json.dumps(chunk).encode() + b"\n\ndata: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    result = make(handler).test(ModelInfo("plain-test", "m"), timeout=5.0)
    assert result.ok is True and result.ttft_ms is not None
    assert seen["auth"] == "Bearer test-key"
    assert seen["url"] == "https://plain.invalid/v1/chat/completions"
    assert seen["body"]["max_tokens"] == 16 and seen["body"]["stream"] is True


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "account"), (402, "account"), (403, "account"), (429, "account"), (408, "transient"),
     (503, "transient"), (400, "model"), (404, "model")],
)  # fmt: skip
def test_default_status_classification(status, kind):
    assert classify_status(status, {}) == kind
    result = make(lambda request: httpx.Response(status, json={"error": {"message": "nope"}})).test(
        ModelInfo("plain-test", "m"), timeout=5.0
    )
    assert result.ok is False and result.failure_kind == kind and result.error == "nope"


def test_default_stream_error_classification():
    assert classify_stream_error(401, {}, classify_status) == "account"
    assert classify_stream_error(403, {}, classify_status) == "account"
    assert classify_stream_error(404, {}, classify_status) == "model"
    assert classify_stream_error(429, {}, classify_status) == "transient"
    assert classify_stream_error(None, {}, classify_status) == "transient"


def test_default_rate_limit_hints_read_retry_after_only():
    assert retry_after_hint({"retry-after": "12"}) == (12.0, None)
    assert retry_after_hint({"retry-after": "999999"}) == (24 * 3600.0, None)
    assert retry_after_hint({"retry-after": "soon"}) == (None, None)
    assert retry_after_hint({"x-ratelimit-reset": "30"}) == (None, None)


def test_close_only_closes_its_own_client():
    provider = Plain(api_key="k")
    client = provider._get_client()
    provider.close()
    assert client.is_closed and provider.client is None
    supplied = httpx.Client()
    with Plain(api_key="k", client=supplied):
        pass
    assert not supplied.is_closed
    supplied.close()
