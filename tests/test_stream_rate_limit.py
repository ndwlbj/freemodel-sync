"""Errors that arrive inside the SSE stream (after HTTP 200) are model failures, not account errors."""

from __future__ import annotations

import json

import httpx
import pytest
import yaml

from freemodel_sync.cli import main
from freemodel_sync.models import ModelInfo
from freemodel_sync.providers.openrouter import OpenRouterProvider
from freemodel_sync.tester import ResultCache, run_tests

#: the error that stopped the 2026-10-23 snapshot after 11 probes
UPSTREAM_TEXT = (
    "xingchen-agi/xing4.0-29b-a4b:free is temporarily rate-limited upstream. Please retry shortly, "
    "or add your own key to accumulate your rate limits: https://openrouter.ai/settings/integrations"
)


def sse(*chunks):
    return b"".join(b"data: " + (c if isinstance(c, bytes) else json.dumps(c).encode()) + b"\n\n" for c in chunks)


OK_STREAM = sse({"choices": [{"delta": {"content": "OK"}}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]})


def stream_error(error):
    """A mid-stream error event, as OpenRouter documents it (finish_reason "error")."""
    return sse(
        {"choices": [{"delta": {"content": ""}}]},
        {"error": error, "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "error"}]},
    )


def probe(body, status=200):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, content=body)))
    return OpenRouterProvider(api_key="test-key", client=client).test(ModelInfo("openrouter", "x/y:free"))


@pytest.mark.parametrize(
    "error",
    [
        {"code": 429, "message": UPSTREAM_TEXT},  # the 10-23 regression
        {"code": "429", "message": UPSTREAM_TEXT},
        {"message": UPSTREAM_TEXT},
        {"code": 429, "message": "Rate limit exceeded", "metadata": {"error_type": "rate_limit_exceeded"}},
        {"code": 502, "message": "Provider returned error"},
        {"code": 408, "message": "upstream timeout"},
        "upstream went away",
    ],
)
def test_mid_stream_rate_limit_and_upstream_errors_are_transient(error):
    result = probe(stream_error(error))
    assert result.ok is False and result.status_code == 200
    assert result.failure_kind == "transient"
    assert not result.is_account_error


def test_mid_stream_other_4xx_is_a_model_failure():
    result = probe(stream_error({"code": 400, "message": "context too long"}))
    assert result.failure_kind == "model"


@pytest.mark.parametrize(
    "error",
    [
        {"code": 401, "message": "User not found"},
        {"code": 402, "message": "Insufficient credits"},
        {"code": 403, "message": "Key limit exceeded", "metadata": {"limit_source": "openrouter_key_limit"}},
    ],
)
def test_mid_stream_explicit_account_codes_still_stop(error):
    assert probe(stream_error(error)).failure_kind == "account"


def test_mid_stream_model_specific_403_is_a_model_failure():
    error = {"code": 403, "message": "flagged", "metadata": {"flagged_input": "x", "error_type": "refusal"}}
    assert probe(stream_error(error)).failure_kind == "model"


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        # pre-stream platform 429 (free-model cap): unchanged, still an account error
        (
            429,
            {
                "error": {
                    "code": 429,
                    "message": "Rate limit exceeded: free-models-per-day",
                    "metadata": {"error_type": "rate_limit_exceeded"},
                }
            },
            "account",
        ),
        # pre-stream upstream 429: unchanged, transient
        (
            429,
            {"error": {"code": 429, "message": "Provider returned error", "metadata": {"provider_name": "SomeHost"}}},
            "transient",
        ),
        (401, {"error": {"code": 401, "message": "User not found"}}, "account"),
        (402, {"error": {"code": 402, "message": "Insufficient credits"}}, "account"),
    ],
)
def test_pre_stream_classification_is_unchanged(status, body, kind):
    assert probe(json.dumps(body).encode(), status=status).failure_kind == kind


def test_round_continues_after_a_mid_stream_rate_limit(tmp_path):
    """Regression for the 2026-10-23 snapshot: probing stopped at the rate-limited model."""
    bodies = {
        "v/a:free": OK_STREAM,
        "xingchen-agi/xing4.0-29b-a4b:free": stream_error({"code": 429, "message": UPSTREAM_TEXT}),
        "v/c:free": OK_STREAM,
    }

    def handler(request):
        return httpx.Response(200, content=bodies[json.loads(request.content)["model"]])

    provider = OpenRouterProvider(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    models = [ModelInfo("openrouter", mid) for mid in bodies]
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, models, cache=cache, max_tests=10, reserve=0)
    assert run.stop_reason is None and run.account_error is None and not run.account_problem
    assert run.probes == 3
    limited = run["openrouter|xingchen-agi/xing4.0-29b-a4b:free"]
    assert limited.failure_kind == "transient" and "rate-limited upstream" in limited.error
    assert run["openrouter|v/c:free"].ok


def test_sync_still_writes_after_a_mid_stream_rate_limit(tmp_path, monkeypatch, models_payload):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    target = tmp_path / "bot-model.yml"
    target.write_text("- id: agent-default-model\n  config: {provider: x, model: 'old'}\n")
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "testing": {"cache_path": str(tmp_path / "cache.json"), "max_tests": 20, "reserve_requests": 0},
                "state_path": str(tmp_path / "state.json"),
                "targets": [{"adapter": "dsh", "path": str(target)}],
            }
        )
    )
    calls = []

    def handler(request):
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json=models_payload)
        if path.endswith("/key"):
            return httpx.Response(
                200, json={"data": {"free_model_daily_requests": {"used": 0, "limit": 50, "remaining": 50}}}
            )
        calls.append(json.loads(request.content)["model"])
        if len(calls) == 1:  # the most promising model is rate-limited mid-stream
            return httpx.Response(200, content=stream_error({"code": 429, "message": UPSTREAM_TEXT}))
        return httpx.Response(200, content=OK_STREAM)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    factory = lambda name, **kw: OpenRouterProvider(api_key="test-key", client=client)
    assert main(["-c", str(cfg), "sync", "--no-notify"], provider_factory=factory) == 0
    assert len(calls) > 1
    model = yaml.safe_load(target.read_text())[0]["config"]["model"]
    assert model != calls[0] and model in calls


def test_groq_inherits_stream_error_rules_and_keeps_pre_stream_429_as_account():
    from freemodel_sync.providers.groq import GroqProvider

    def make(status, body):
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, content=body)))
        return GroqProvider(api_key="gsk-test", client=client, plan="free")

    model = ModelInfo("groq", "llama-x")
    mid = make(200, stream_error({"code": 429, "message": "over capacity"})).test(model)
    assert mid.failure_kind == "transient"
    pre = make(429, json.dumps({"error": {"code": 429, "message": "rate limit"}}).encode()).test(model)
    assert pre.failure_kind == "account"
