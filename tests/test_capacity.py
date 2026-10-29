"""capacity failures: classification, short TTL, separate streak, ranking penalty and downgrade."""

from __future__ import annotations

import time

import pytest

from freemodel_sync import spec
from freemodel_sync.models import ModelInfo, TestResult
from freemodel_sync.providers.bailian import BailianProvider
from freemodel_sync.ranking import RankWeights, rank, score_model
from freemodel_sync.tester import ResultCache, run_tests


def test_queue_and_no_capacity_are_capacity() -> None:
    for status, code in ((429, "ModelUnavailable"), (400, "ModelBusy"), (403, "ModelUnavailable")):
        assert BailianProvider._classify(status, {"code": code}) == "capacity"
    # A bare 429 is a normal rate limit, and 5xx stays transient.
    assert BailianProvider._classify(429, {}) == "transient"
    assert BailianProvider._classify(503, {"code": "ModelUnavailable"}) == "transient"


def test_capacity_gets_the_short_ttl_but_its_own_streak(tmp_path) -> None:
    cache = ResultCache(tmp_path / "cache.json").load()
    key = "p|busy"
    cache.put(TestResult(key=key, ok=False, failure_kind="capacity", error="queued", tested_at=time.time()))
    assert cache._results[key].capacity_streak == 1
    cache.put(TestResult(key=key, ok=False, failure_kind="capacity", error="queued", tested_at=time.time()))
    assert cache._results[key].capacity_streak == 2
    # A transient result breaks the capacity streak but not the other way round.
    cache.put(TestResult(key=key, ok=False, failure_kind="transient", error="503", tested_at=time.time()))
    cache.put(TestResult(key=key, ok=False, failure_kind="capacity", error="queued", tested_at=time.time()))
    assert cache._results[key].capacity_streak == 1
    cache.put(TestResult(key=key, ok=True, tested_at=time.time()))
    assert cache._results[key].capacity_streak == 0

    old = time.time() - 3600
    cache.put(TestResult(key="p|old", ok=False, failure_kind="capacity", error="queued", tested_at=old))
    # capacity expires after the short transient TTL, like transient.
    assert cache.get("p|old", 6 * 3600, 1800) is None
    assert cache.get("p|old", 6 * 3600, 2 * 3600) is not None


def test_run_tests_counts_capacity_without_stopping_the_round(tmp_path) -> None:
    class Provider:
        name = "p"

        def __init__(self) -> None:
            self.calls = []

        def test(self, model, timeout=30.0):
            self.calls.append(model.id)
            return TestResult(
                key=model.key,
                ok=False,
                error="queued",
                failure_kind="capacity",
                status_code=429,
                tested_at=time.time(),
            )

    models = [ModelInfo("p", "a"), ModelInfo("p", "b")]
    provider = Provider()
    cache = ResultCache(tmp_path / "cache.json").load()
    run = run_tests(provider, models, cache=cache, max_tests=2)
    assert provider.calls == ["a", "b"]
    assert run.stop_reason is None and not run.account_problem
    assert run["p|a"].capacity_streak == 1 and run["p|b"].capacity_streak == 1
    # The same cache counts the second probe round separately per model.
    run2 = run_tests(provider, models, cache=cache, max_tests=2, cache_ttl_s=0, transient_ttl_s=0)
    assert run2["p|a"].capacity_streak == 2


def test_capacity_is_penalised_then_downgraded_after_n() -> None:
    model = ModelInfo("p", "busy", context_length=131072, supports_tools=True)
    weights = RankWeights()
    downgrade_after = int(spec.ranking_spec()["capacity"]["downgradeAfter"])
    first = TestResult(model.key, False, error="queued", failure_kind="capacity", capacity_streak=1)
    score1, reasons1 = score_model(model, first, weights)
    assert score1 == pytest.approx(-weights.capacity_penalty)
    assert any("capacity" in reason and "retried" in reason for reason in reasons1)

    downgraded = TestResult(
        model.key,
        False,
        error="queued",
        failure_kind="capacity",
        capacity_streak=downgrade_after,
    )
    score_n, reasons_n = score_model(model, downgraded, weights)
    assert score_n == pytest.approx(spec.ranking_spec()["score"]["failedScore"])
    assert any("downgraded" in reason for reason in reasons_n)

    # The threshold is configurable.
    score_custom, _ = score_model(model, downgraded, weights, capacity_downgrade_after=2)
    assert score_custom == pytest.approx(spec.ranking_spec()["score"]["failedScore"])


def test_capacity_ranks_below_untested_but_above_a_hard_failure() -> None:
    untested = ModelInfo("p", "a-untested")
    busy = ModelInfo("p", "b-busy")
    dead = ModelInfo("p", "c-dead")
    results = {
        busy.key: TestResult(busy.key, False, error="queued", failure_kind="capacity", capacity_streak=1),
        dead.key: TestResult(dead.key, False, error="gone", failure_kind="model"),
    }
    order = [item.model.id for item in rank([busy, dead, untested], results)]
    assert order == ["a-untested", "b-busy", "c-dead"]


def test_threshold_comes_from_the_shared_spec_and_is_configurable() -> None:
    from freemodel_sync.config import Config, ConfigError, _parse_ranking

    assert spec.ranking_spec()["capacity"]["downgradeAfter"] == 3
    assert Config().ranking.capacity_downgrade_after == 3
    assert _parse_ranking({"capacity_downgrade_after": 5}).capacity_downgrade_after == 5
    with pytest.raises(ConfigError):
        _parse_ranking({"capacity_downgrade_after": 0})
