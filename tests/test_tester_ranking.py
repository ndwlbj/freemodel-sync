from __future__ import annotations

import json
import time
from datetime import date

from freemodel_sync.models import ModelInfo, TestResult
from freemodel_sync.ranking import RankWeights, filter_models, rank, score_model, select
from freemodel_sync.tester import ResultCache, run_tests


class FakeProvider:
    name = "fake"

    def __init__(self, ok_ids=()):
        self.ok_ids = set(ok_ids)
        self.calls = []

    def test(self, model, timeout=30.0):
        self.calls.append(model.id)
        return TestResult(key=model.key, ok=model.id in self.ok_ids, ttft_ms=200.0, tested_at=time.time())


def mk(n, **kw):
    return [ModelInfo("fake", f"m{i}:free", **kw) for i in range(n)]


def test_run_tests_caps_and_caches(tmp_path):
    cache_path = tmp_path / "c" / "results.json"
    provider = FakeProvider(ok_ids={"m0:free"})
    models = mk(5)
    res = run_tests(provider, models, cache=ResultCache(cache_path).load(), max_tests=2)
    assert list(res) == ["fake|m0:free", "fake|m1:free"]
    assert provider.calls == ["m0:free", "m1:free"]
    data = json.loads(cache_path.read_text())
    assert data["daily"]["count"] == 2

    provider2 = FakeProvider()
    res2 = run_tests(provider2, models, cache=ResultCache(cache_path).load(), max_tests=2)
    assert res2["fake|m0:free"].cached is True and res2["fake|m0:free"].ok is True
    assert provider2.calls == ["m2:free", "m3:free"]


def test_run_tests_respects_daily_budget(tmp_path):
    cache = ResultCache(tmp_path / "r.json").load()
    cache.add_requests(8)
    provider = FakeProvider()
    run_tests(provider, mk(5), cache=cache, max_tests=5, daily_budget=20, reserve=10)
    # 8 used: probes 9 and 10 still leave the 10-request reserve; the 3rd would not
    assert len(provider.calls) == 2


def test_cache_tolerates_corrupt_file(tmp_path):
    p = tmp_path / "r.json"
    p.write_text("{not json")
    cache = ResultCache(p).load()
    assert cache.requests_today() == 0
    assert cache.get("x", 100) is None


def test_cache_expiry(tmp_path):
    cache = ResultCache(tmp_path / "r.json").load()
    cache.put(TestResult(key="k", ok=True, tested_at=time.time() - 7200))
    assert cache.get("k", 3600) is None
    assert cache.get("k", 10800).cached is True


def test_filter_models():
    today = date(2026, 10, 1)
    models = [
        ModelInfo("p", "a/tools:free", context_length=128000, supports_tools=True),
        ModelInfo("p", "a/small:free", context_length=4096),
        ModelInfo("p", "a/expiring:free", context_length=128000, expiration_date=date(2026, 10, 3)),
        ModelInfo("p", "b/other:free", context_length=128000),
    ]
    ids = lambda ms: [m.id for m in ms]
    assert ids(filter_models(models, require_tools=True)) == ["a/tools:free"]
    assert "a/small:free" not in ids(filter_models(models, min_context=8000))
    assert "a/expiring:free" not in ids(filter_models(models, exclude_expiring_within_days=3, today=today))
    assert ids(filter_models(models, include=["a/*"], exclude=["*small*"])) == ["a/tools:free", "a/expiring:free"]


def test_scoring_and_selection():
    today = date(2026, 10, 1)
    fast = ModelInfo("p", "fast:free", context_length=131072, supports_tools=True)
    slow = ModelInfo("p", "slow:free", context_length=131072)
    broken = ModelInfo("p", "broken:free", context_length=1_000_000, supports_tools=True)
    untested = ModelInfo("p", "untested:free", context_length=32768)
    expiring = ModelInfo("p", "expiring:free", context_length=131072, supports_tools=True,
                         expiration_date=date(2026, 10, 6))
    results = {
        fast.key: TestResult(fast.key, True, ttft_ms=300),
        slow.key: TestResult(slow.key, True, ttft_ms=8000),
        broken.key: TestResult(broken.key, False, error="429"),
        expiring.key: TestResult(expiring.key, True, ttft_ms=300),
    }
    ranked = rank([slow, broken, untested, fast, expiring], results, today=today)
    order = [r.model.id for r in ranked]
    assert order[0] == "fast:free"
    assert order.index("expiring:free") > order.index("fast:free")
    assert order[-1] == "broken:free"
    assert any("expires in" in r for r in ranked[order.index("expiring:free")].reasons)

    sel = select(ranked, fallback_count=3)
    assert sel.primary.model.id == "fast:free"
    fb = [f.model.id for f in sel.fallbacks]
    assert "broken:free" not in fb
    assert fb[-1] == "untested:free"  # untested only fills remaining slots


def test_select_none_when_nothing_works():
    m = ModelInfo("p", "x:free")
    assert select(rank([m], {m.key: TestResult(m.key, False)})) is None
    assert select(rank([m], {})) is None


def test_weights_are_configurable():
    m = ModelInfo("p", "x:free", supports_tools=True)
    s1, _ = score_model(m, TestResult(m.key, True), RankWeights(tools=0))
    s2, _ = score_model(m, TestResult(m.key, True), RankWeights(tools=50))
    assert s2 - s1 == 50
