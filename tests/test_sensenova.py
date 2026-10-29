"""SenseNova provider: plan gate, allowlist/catalogue intersection, pricing, errors (mocked HTTP)."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers import ProviderError, get_provider_class
from freemodel_sync.providers.sensenova import SenseNovaProvider

KEY = "sk-test"


def model(
    model_id: str,
    *,
    pricing: Any = "0",
    context: int = 131072,
    features: Any = None,
    businesses: Any = None,
) -> Dict[str, Any]:
    raw: Dict[str, Any] = {"id": model_id, "pricing": pricing, "context_length": context}
    if features is not None:
        raw["supported_features"] = features
    if businesses is not None:
        raw["businesses"] = businesses
    return raw


MODELS = {
    "object": "list",
    "data": [
        model("deepseek-v4-flash", features=["text", "function_call"]),
        model(
            "sensenova-6.8-flash-lite",
            features=["text", "image", "reasoning"],
            businesses=["vision"],
        ),
        # Present in the catalogue but not on the default allowlist.
        model("sensenova-6.8-pro", pricing="0.02"),
        {"id": "", "pricing": "0"},
    ],
}


def sensenova(handler, api_key: str | None = KEY, **options) -> SenseNovaProvider:
    options.setdefault("plan", "token-plan")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SenseNovaProvider(api_key=api_key, client=client, **options)


def sse(*chunks: Any) -> bytes:
    return "".join(f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks).encode()


def test_registered_with_own_key_env_base_url_and_tier():
    cls = get_provider_class("sensenova")
    assert cls is SenseNovaProvider
    assert cls.api_key_env == "SENSENOVA_API_KEY"
    assert cls.base_url == "https://token.sensenova.cn/v1"
    assert cls.auth_kind == "api_key"
    assert cls.tier == 1
    # The P7 base-class hook defaults to unknown; SenseNova derives it from the catalogue.
    assert SenseNovaProvider(api_key=KEY).capabilities_for(ModelInfo("sensenova", "x")).source == "unknown"


@pytest.mark.parametrize("plan", [None, "", "free", "token plan??"])
def test_requires_token_plan_confirmation_and_sends_nothing(plan):
    calls = []
    provider = sensenova(lambda request: calls.append(request) or httpx.Response(200, json=MODELS), plan=plan)
    with pytest.raises(ProviderError, match="plan: token-plan"):
        provider.discover()
    with pytest.raises(ProviderError, match="plan: token-plan"):
        provider.test(ModelInfo("sensenova", "deepseek-v4-flash"))
    assert calls == []


def test_discover_intersects_default_allowlist_with_catalogue_and_reads_capabilities():
    seen: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=MODELS)

    models = sensenova(handler).discover()
    assert [m.id for m in models] == ["deepseek-v4-flash", "sensenova-6.8-flash-lite"]
    assert seen == {"url": "https://token.sensenova.cn/v1/models", "auth": f"Bearer {KEY}"}

    flash = models[0]
    assert flash.supports_tools is True and flash.context_length == 131072
    lite = models[1]
    assert lite.capabilities.vision is True
    assert lite.capabilities.reasoning is True
    assert lite.capabilities.tools is None  # absence is unknown, never false
    assert lite.capabilities.source == "catalog"


def test_configured_allowlist_is_intersected_with_the_catalogue():
    models = sensenova(
        lambda request: httpx.Response(200, json=MODELS),
        models=["deepseek-v4-flash", "not-in-the-catalogue", "deepseek-v4-flash"],
    ).discover()
    assert [m.id for m in models] == ["deepseek-v4-flash"]


def test_empty_configured_allowlist_uses_catalogue_pricing_zero():
    models = sensenova(lambda request: httpx.Response(200, json=MODELS), models=[]).discover()
    assert [m.id for m in models] == ["deepseek-v4-flash", "sensenova-6.8-flash-lite"]


def test_non_zero_or_numeric_pricing_is_removed_with_a_warning(caplog):
    payload = {
        "data": [
            model("deepseek-v4-flash", pricing="0.000001"),
            model("sensenova-6.8-flash-lite", pricing="0"),
            model("numeric-zero", pricing=0),
        ]
    }
    with caplog.at_level("WARNING"):
        models = sensenova(
            lambda request: httpx.Response(200, json=payload),
            models=["deepseek-v4-flash", "sensenova-6.8-flash-lite", "numeric-zero"],
        ).discover()
    assert [m.id for m in models] == ["sensenova-6.8-flash-lite"]
    warnings = " ".join(record.getMessage() for record in caplog.records)
    assert "deepseek-v4-flash" in warnings and "not the string" in warnings
    assert "numeric-zero" in warnings


def test_catalogue_failure_falls_back_to_the_confirmed_allowlist():
    models = sensenova(lambda request: httpx.Response(503, json={}), models=["deepseek-v4-flash"]).discover()
    assert [m.id for m in models] == ["deepseek-v4-flash"]
    assert models[0].context_length == 0
    assert models[0].capabilities.source == "unknown"


def test_discover_needs_a_key():
    calls = []
    with pytest.raises(ProviderError, match="SENSENOVA_API_KEY"):
        sensenova(lambda request: calls.append(request), api_key=None).discover()
    assert calls == []


@pytest.mark.parametrize(
    "status, kind",
    [(401, "account"), (403, "model"), (429, "transient"), (500, "transient"), (400, "model")],
)
def test_error_classification(status, kind):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "x"}})

    result = sensenova(handler).test(ModelInfo("sensenova", "deepseek-v4-flash"))
    assert result.ok is False
    assert result.failure_kind == kind
    assert result.status_code == status


def test_sse_success_path_uses_max_tokens_and_measures_ttft():
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=sse(
                {"choices": [{"delta": {"content": "OK"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                "[DONE]",
            ),
            headers={"content-type": "text/event-stream"},
        )

    result = sensenova(handler).test(ModelInfo("sensenova", "sensenova-6.8-flash-lite"))
    assert result.ok is True
    assert result.ttft_ms is not None
    assert captured["body"]["stream"] is True
    assert captured["body"]["model"] == "sensenova-6.8-flash-lite"
    assert captured["body"]["max_tokens"] == 16


def test_quota_is_public_beta_and_copies_free_until():
    quota = sensenova(lambda request: httpx.Response(500), free_until="2026-12-31").quota()
    assert quota.period == "beta"
    assert quota.unit == "unknown"
    assert quota.source == "none"
    assert quota.expires_at == "2026-12-31"
    assert quota.remaining_today is None
    assert quota.to_dict()["remaining_total"] is None
