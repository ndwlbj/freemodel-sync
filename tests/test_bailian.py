"""Bailian: guard + allowlist, manual per-model quota, distilled tools=false, quota stop (mocked HTTP)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import pytest

from freemodel_sync.models import ModelInfo
from freemodel_sync.providers import ProviderError, get_provider_class
from freemodel_sync.providers.bailian import BailianProvider
from freemodel_sync.tester import ResultCache, next_utc_midnight, run_tests

KEY = "sk-test"


def model(model_id: str, **extra: Any) -> Dict[str, Any]:
    return {"id": model_id, "context_length": 131072, **extra}


CATALOG = {
    "object": "list",
    "data": [
        model("deepseek-v3.2"),
        model("qwen3-8b-distill"),
        model("not-in-the-allowlist"),
        {"id": ""},
    ],
}


def bailian(handler, api_key: str | None = KEY, **options) -> BailianProvider:
    options.setdefault("free_quota_guard", "confirmed")
    options.setdefault("models", ["deepseek-v3.2"])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BailianProvider(api_key=api_key, client=client, **options)


def sse(*chunks: Any) -> bytes:
    return "".join(f"data: {c if isinstance(c, str) else json.dumps(c)}\n\n" for c in chunks).encode()


def test_registered_with_region_base_url_key_env_and_tier() -> None:
    cls = get_provider_class("bailian")
    assert cls is BailianProvider
    assert cls.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert cls.api_key_env == "DASHSCOPE_API_KEY"
    assert cls.auth_kind == "api_key"
    assert cls.tier == 1


@pytest.mark.parametrize(
    "options",
    [
        {"free_quota_guard": None, "models": ["deepseek-v3.2"]},
        {"free_quota_guard": "yes", "models": ["deepseek-v3.2"]},
        {"free_quota_guard": "confirmed", "models": []},
        {"free_quota_guard": "confirmed", "models": ["", "  "]},
    ],
)
def test_without_guard_or_allowlist_nothing_is_listed_and_no_request_is_sent(options, caplog) -> None:
    calls = []
    provider = bailian(lambda request: calls.append(request) or httpx.Response(200, json=CATALOG), **options)
    with caplog.at_level("WARNING"):
        assert provider.discover() == []
    assert calls == []
    warnings = " ".join(record.getMessage() for record in caplog.records)
    assert "free_quota_guard" in warnings or "models is empty" in warnings


def test_discover_intersects_the_allowlist_and_builds_manual_total_quotas() -> None:
    seen: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=CATALOG)

    provider = bailian(
        handler,
        models=[
            {"id": "deepseek-v3.2", "quota": {"unit": "tokens", "period": "total", "limit": 1000000}},
            {"id": "qwen3-8b-distill", "quota_tokens": 500000},
            {"id": "not-in-the-catalogue", "quota": {"limit": 1}},
        ],
    )
    models = provider.discover()
    assert [m.id for m in models] == ["deepseek-v3.2", "qwen3-8b-distill"]
    assert seen == {
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        "auth": f"Bearer {KEY}",
    }

    first = models[0].quota
    assert first is not None
    assert (first.unit, first.period, first.limit, first.source, first.scope) == (
        "tokens",
        "total",
        1000000.0,
        "manual",
        "model",
    )
    assert first.remaining_total == 1000000
    assert models[1].quota is not None and models[1].quota.limit == 500000


def test_distilled_models_have_tools_false_and_string_ids_have_unknown_manual_quota() -> None:
    models = bailian(
        lambda request: httpx.Response(200, json=CATALOG),
        models=["deepseek-v3.2", "qwen3-8b-distill"],
    ).discover()
    assert models[0].supports_tools is False and models[0].capabilities.tools is None
    assert models[1].capabilities.tools is False
    assert models[1].capabilities.source == "config"
    plain = bailian(lambda request: httpx.Response(200, json={}), models=["deepseek-v3.2"]).discover()[0]
    assert plain.quota is not None
    assert plain.quota.period == "total" and plain.quota.source == "manual"
    assert plain.quota.unit == "unknown" and plain.quota.limit is None


def test_catalogue_failure_falls_back_to_the_confirmed_allowlist() -> None:
    models = bailian(lambda request: httpx.Response(503, json={}), models=["deepseek-v3.2"]).discover()
    assert [m.id for m in models] == ["deepseek-v3.2"]
    assert models[0].context_length == 0


def test_discover_needs_a_key() -> None:
    calls = []
    with pytest.raises(ProviderError, match="DASHSCOPE_API_KEY"):
        bailian(lambda request: calls.append(request), api_key=None).discover()
    assert calls == []


@pytest.mark.parametrize(
    "status,error,kind",
    [
        (401, {}, "account"),
        (403, {"code": "AllocationQuota.FreeTierOnly"}, "quota"),
        (403, {"code": "AccessDenied"}, "model"),
        (429, {"code": "ModelUnavailable"}, "capacity"),
        (429, {}, "transient"),
        (500, {}, "transient"),
        (400, {}, "model"),
    ],
)
def test_error_classification(status, error, kind) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {**error, "message": "x"}})

    result = bailian(handler).test(ModelInfo("bailian", "deepseek-v3.2"))
    assert result.ok is False
    assert result.failure_kind == kind
    assert result.status_code == status


def test_quota_error_stops_the_channel_for_the_rest_of_the_utc_day(tmp_path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            403,
            json={"error": {"code": "AllocationQuota.FreeTierOnly", "message": "free quota exhausted"}},
        )

    provider = bailian(handler, models=["deepseek-v3.2", "qwen3-8b-distill"])
    models = [ModelInfo("bailian", "deepseek-v3.2"), ModelInfo("bailian", "qwen3-8b-distill")]
    cache = ResultCache(tmp_path / "cache.json").load()
    run = run_tests(provider, models, cache=cache, max_tests=2)
    assert len(calls) == 1
    assert run.quota_error is not None and run.quota_error.failure_kind == "quota"
    assert run.account_problem is True
    assert "stopped until the next UTC day" in (run.stop_reason or "")
    assert cache.blocked_until == pytest.approx(next_utc_midnight(), abs=5)
    assert datetime.fromtimestamp(cache.blocked_until, timezone.utc).hour == 0
    assert "bailian|deepseek-v3.2" not in run

    again = run_tests(provider, models, cache=ResultCache(tmp_path / "cache.json").load(), max_tests=2)
    assert len(calls) == 1
    assert again.rate_limited is True and again.probes == 0


def test_sse_success_path_uses_streaming_and_max_tokens() -> None:
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

    result = bailian(handler).test(ModelInfo("bailian", "deepseek-v3.2"))
    assert result.ok is True and result.ttft_ms is not None
    assert captured["body"]["stream"] is True
    assert captured["body"]["model"] == "deepseek-v3.2"
    assert captured["body"]["max_tokens"] == 16
