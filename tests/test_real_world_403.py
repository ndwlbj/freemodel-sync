"""Regression tests from the 0.3.0 real-world run (2026-10-22).

A free OpenRouter model answered a probe with a *model-specific* 403
("... is only available on agentic harnesses", routing metadata). 0.3.0
treated every 403 as an account error, so probing stopped at that model on
every run (nothing was cached) and the models behind it were never tested.
"""

from __future__ import annotations

import json

import httpx
import pytest

from freemodel_sync.cli import _status
from freemodel_sync.models import ModelInfo, TestResult
from freemodel_sync.providers.openrouter import OpenRouterProvider, _classify
from freemodel_sync.ranking import RankWeights, score_model
from freemodel_sync.tester import ResultCache, run_tests

#: shape of the real response body (model id replaced)
HARNESS_403 = {
    "error": {
        "message": "vendor/gated:free is only available on agentic harnesses. Try plugging it into a "
        "coding agent or productivity app listed on https://openrouter.ai/apps",
        "code": 403,
        "metadata": {
            "routing_funnel": [{"step": "Initial Endpoints", "endpoint_count": 1}],
            "failed_routing_step": "Gate Free Endpoints by Agentic Harness",
        },
    }
}
BUDGET_403 = {
    "error": {
        "code": 403,
        "message": "Budget limit exceeded (weekly limit). $52.00 of $50.00 used; resets 2026-10-12T00:00:00.000Z.",
        "metadata": {"limit_source": "openrouter_key_limit", "scope": "key_limit", "limit_usd": 50},
    }
}
GUARDRAIL_403 = {
    "error": {
        "code": 403,
        "message": "Request blocked: prompt injection patterns detected",
        "metadata": {"patterns": ["ignore all previous instructions"]},
    }
}
MODERATION_403 = {
    "error": {
        "code": 403,
        "message": "vendor/m:free requires moderation",
        "metadata": {"reasons": ["x"], "flagged_input": "...", "provider_name": "Host", "model_slug": "vendor/m"},
    }
}
POLICY_403 = {"error": {"code": 403, "message": "blocked", "metadata": {"error_type": "content_policy_violation"}}}
OK_STREAM = (
    b'data: {"choices": [{"delta": {"content": "OK"}}]}\n\n'
    b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n'
)


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        (HARNESS_403, "model"),
        (MODERATION_403, "model"),
        (POLICY_403, "model"),
        (BUDGET_403, "account"),
        (GUARDRAIL_403, "account"),
        ({"error": {"code": 403, "message": "Forbidden"}}, "account"),
        ({}, "account"),
    ],
)
def test_403_classification(body, kind):
    assert _classify(403, body.get("error", {})) == kind


def test_budget_wins_over_model_metadata():
    error = {"code": 403, "metadata": {"limit_source": "openrouter_workspace_budget", "provider_name": "Host"}}
    assert _classify(403, error) == "account"


def test_401_402_still_account():
    assert _classify(401, {}) == "account"
    assert _classify(402, {"metadata": {"provider_name": "Host"}}) == "account"


def test_gated_model_does_not_stop_probing(tmp_path):
    calls = []

    def handler(request):
        model = json.loads(request.content)["model"]
        calls.append(model)
        if model == "vendor/gated:free":
            return httpx.Response(403, json=HARNESS_403)
        return httpx.Response(200, content=OK_STREAM)

    provider = OpenRouterProvider(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    models = [ModelInfo("openrouter", mid, context_length=65536) for mid in ("vendor/gated:free", "a:free", "b:free")]
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, models, cache=cache, max_tests=5)

    assert calls == ["vendor/gated:free", "a:free", "b:free"]
    assert run.account_error is None
    gated = cache.get("openrouter|vendor/gated:free", 3600)
    assert gated is not None and not gated.ok and gated.failure_kind == "model" and gated.status_code == 403
    assert "agentic harnesses" in (gated.error or "")

    # the next run reuses the cached failure: no request to the gated model again
    calls.clear()
    run_tests(provider, models, cache=cache, max_tests=5)
    assert "vendor/gated:free" not in calls


def test_budget_403_still_stops_probing(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403, json=BUDGET_403)

    provider = OpenRouterProvider(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    models = [ModelInfo("openrouter", f"m{i}:free", context_length=65536) for i in range(3)]
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, models, cache=cache, max_tests=5)
    assert len(calls) == 1 and run.account_error is not None
    assert cache.get("openrouter|m0:free", 3600) is None


def test_transient_failures_are_labelled_as_such():
    model = ModelInfo("openrouter", "busy:free", context_length=65536)
    transient = TestResult(
        "openrouter|busy:free", False, error="Provider returned error", status_code=429, failure_kind="transient"
    )
    dead = TestResult(
        "openrouter|dead:free", False, error="Provider returned error", status_code=404, failure_kind="model"
    )
    assert _status(transient) == "transient"
    assert _status(dead) == "failed"
    score, reasons = score_model(model, transient, RankWeights())
    assert score == -1000.0 and reasons[0].startswith("temporarily unavailable 429")
    assert score_model(model, dead, RankWeights())[1][0].startswith("failed:")
