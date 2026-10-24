"""Regression tests: free quota, account-level errors, missing key (review P0-1..3)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx
import pytest
import yaml

from freemodel_sync.cli import EXIT_ACCOUNT_ERROR, main
from freemodel_sync.models import ModelInfo, TestResult
from freemodel_sync.providers.openrouter import OpenRouterProvider
from freemodel_sync.tester import ResultCache, run_tests


def sse(*chunks):
    return b"".join(b"data: " + (c if isinstance(c, bytes) else json.dumps(c).encode()) + b"\n\n" for c in chunks)


OK_STREAM = sse({"choices": [{"delta": {"content": "OK"}}]}, {"choices": [{"delta": {}, "finish_reason": "stop"}]})
PLATFORM_429 = {"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day",
                          "metadata": {"error_type": "rate_limit_exceeded"}}}
UPSTREAM_429 = {"error": {"code": 429, "message": "Provider returned error",
                          "metadata": {"provider_name": "SomeHost", "raw": "busy"}}}


class FakeOpenRouter:
    """A tiny stand-in for the OpenRouter API, served through httpx.MockTransport."""

    def __init__(self, models_payload, *, remaining=2, limit=50, chat=None):
        self.models_payload = models_payload
        self.remaining = remaining
        self.limit = limit
        self.chat = chat or (lambda request: httpx.Response(200, content=OK_STREAM))
        self.chat_calls = 0
        self.key_calls = 0

    def __call__(self, request):
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json=self.models_payload)
        if path.endswith("/key"):
            self.key_calls += 1
            return httpx.Response(200, json={"data": {
                "is_free_tier": False, "usage": 0,
                "free_model_daily_requests": {"used": self.limit - self.remaining,
                                              "limit": self.limit, "remaining": self.remaining}}})
        if path.endswith("/chat/completions"):
            self.chat_calls += 1
            return self.chat(request)
        return httpx.Response(404)

    def factory(self, api_key="test-key"):
        client = httpx.Client(transport=httpx.MockTransport(self))
        return lambda name, **kw: OpenRouterProvider(api_key=api_key, client=client)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    target = tmp_path / "bot-model.yml"
    target.write_text("- id: agent-default-model\n  config: {provider: x, model: 'old'}\n")
    cfg = tmp_path / "config.yml"
    cfg.write_text(yaml.safe_dump({
        "testing": {"cache_path": str(tmp_path / "cache.json"), "max_tests": 20, "reserve_requests": 0},
        "state_path": str(tmp_path / "state.json"),
        "targets": [{"adapter": "dsh", "path": str(target)}],
    }))
    return tmp_path, cfg, target


# --- P0-1: free_model_daily_requests is the source of truth --------------------------------

def test_remaining_from_key_endpoint_caps_probes(env, models_payload):
    tmp, cfg, _ = env
    api = FakeOpenRouter(models_payload, remaining=3, limit=1000)
    assert main(["-c", str(cfg), "test"], provider_factory=api.factory()) == 0
    assert api.chat_calls == 3  # not 20 (max_tests), not 1000 inferred from is_free_tier=False


def test_reserve_is_subtracted_from_remaining(tmp_path):
    provider = FakeProbe()
    run = run_tests(provider, mk(10), cache=ResultCache(tmp_path / "c.json").load(),
                    max_tests=10, remaining_budget=12, reserve=10)
    assert run.probes == 2 and "budget" in run.stop_reason


def test_daily_counter_uses_utc_day(tmp_path):
    p = tmp_path / "c.json"
    utc_today = datetime.now(timezone.utc).date().isoformat()
    p.write_text(json.dumps({"daily": {"date": utc_today, "count": 7}}))
    assert ResultCache(p).load().requests_today() == 7
    p.write_text(json.dumps({"daily": {"date": "2000-01-01", "count": 7}}))
    assert ResultCache(p).load().requests_today() == 0


def test_config_override_beats_reported_quota(env, models_payload):
    tmp, cfg, _ = env
    data = yaml.safe_load(cfg.read_text())
    data["testing"]["daily_free_limit"] = 2
    cfg.write_text(yaml.safe_dump(data))
    api = FakeOpenRouter(models_payload, remaining=500, limit=1000)
    main(["-c", str(cfg), "test"], provider_factory=api.factory())
    assert api.chat_calls == 2


# --- P0-2: account-level errors stop the round and are not cached ---------------------------

def test_review_repro_platform_429_stops_immediately(env, models_payload):
    tmp, cfg, target = env
    before = target.read_text()
    api = FakeOpenRouter(models_payload, remaining=2,
                         chat=lambda r: httpx.Response(429, json=PLATFORM_429,
                                                       headers={"Retry-After": "120",
                                                                "X-RateLimit-Remaining": "0"}))
    rc = main(["-c", str(cfg), "sync"], provider_factory=api.factory())
    assert rc == EXIT_ACCOUNT_ERROR
    assert api.chat_calls == 1                      # previously: 18
    cache = json.loads((tmp / "cache.json").read_text())
    assert not [k for k in cache if "|" in k]       # no model recorded as failed
    assert cache["blocked_until"] > time.time() + 60
    assert target.read_text() == before

    # Next run before Retry-After expires: no probes at all.
    rc = main(["-c", str(cfg), "sync"], provider_factory=api.factory())
    assert rc == EXIT_ACCOUNT_ERROR and api.chat_calls == 1

    # Once the block expires and the account works again, sync succeeds right away
    # (models were never cached as failures).
    cache["blocked_until"] = time.time() - 1
    (tmp / "cache.json").write_text(json.dumps(cache))
    api.chat = lambda r: httpx.Response(200, content=OK_STREAM)
    assert main(["-c", str(cfg), "sync", "--no-notify"], provider_factory=api.factory()) == 0
    assert "model: 'old'" not in target.read_text()


@pytest.mark.parametrize("status", [401, 402, 403])
def test_auth_and_credit_errors_are_account_level(tmp_path, status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"code": status, "message": "nope"}})

    provider = OpenRouterProvider(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, mk(5, provider="openrouter"), cache=cache, max_tests=5)
    assert len(calls) == 1 and len(run) == 0
    assert run.account_error.status_code == status
    assert cache.get("openrouter|m0:free", 3600) is None


def test_mid_stream_429_is_transient_not_account_level():
    """After HTTP 200 the request was admitted: a 429 in the stream is about the model's upstream.

    (Until fix/stream-rate-limit this was an account error and stopped the round; see
    tests/test_stream_rate_limit.py.) Platform caps still arrive as a pre-stream 429.
    """
    body = sse({"error": {"code": 429, "message": "Rate limit exceeded"},
                "choices": [{"delta": {"content": ""}, "finish_reason": "error"}]})
    provider = OpenRouterProvider(api_key="k", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))))
    result = provider.test(ModelInfo("openrouter", "x:free"))
    assert result.ok is False and result.failure_kind == "transient"


def test_upstream_429_is_transient_and_probing_continues(tmp_path):
    seen = []

    def handler(request):
        model = json.loads(request.content)["model"]
        seen.append(model)
        if model == "m0:free":
            return httpx.Response(429, json=UPSTREAM_429)
        return httpx.Response(200, content=OK_STREAM)

    provider = OpenRouterProvider(api_key="k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, mk(3, provider="openrouter"), cache=cache, max_tests=3, transient_ttl_s=1800)
    assert seen == ["m0:free", "m1:free", "m2:free"]
    failed = run["openrouter|m0:free"]
    assert failed.ok is False and failed.failure_kind == "transient"
    # transient failures expire after transient_ttl_s, not the full cache TTL
    cache._results["openrouter|m0:free"].tested_at = time.time() - 3600
    assert cache.get("openrouter|m0:free", 6 * 3600, 1800) is None
    assert cache.get("openrouter|m1:free", 6 * 3600, 1800) is not None


def test_x_ratelimit_remaining_stops_probing(tmp_path):
    def handler(request):
        return httpx.Response(200, content=OK_STREAM,
                              headers={"X-RateLimit-Remaining": "1",
                                       "X-RateLimit-Reset": str(int((time.time() + 30) * 1000))})

    provider = OpenRouterProvider(api_key="k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, mk(5, provider="openrouter"), cache=cache, max_tests=5, reserve=1)
    assert run.probes == 1 and "X-RateLimit-Remaining" in run.stop_reason
    assert 0 < cache.blocked_until - time.time() <= 31


def test_legacy_cached_account_errors_are_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"p|m:free": TestResult("p|m:free", False, error="missing api key",
                                                    failure_kind="account", tested_at=time.time()).to_dict()}))
    assert ResultCache(p).load().get("p|m:free", 3600) is None


# --- P0-3: no key -> clear error, no probes, no cache writes, no counting -------------------

@pytest.mark.parametrize("command", ["test", "rank", "sync"])
def test_missing_key_errors_out_without_side_effects(env, models_payload, capsys, command):
    tmp, cfg, target = env
    before = target.read_text()
    api = FakeOpenRouter(models_payload)
    rc = main(["-c", str(cfg), command], provider_factory=api.factory(api_key=None))
    assert rc == 1
    err = capsys.readouterr().err
    assert "OPENROUTER_API_KEY is not set" in err
    assert api.chat_calls == 0 and api.key_calls == 0
    assert not (tmp / "cache.json").exists()
    assert target.read_text() == before


def test_discover_still_works_without_key(env, models_payload):
    _, cfg, _ = env
    api = FakeOpenRouter(models_payload)
    assert main(["-c", str(cfg), "discover"], provider_factory=api.factory(api_key=None)) == 0


# --- helpers --------------------------------------------------------------------------------

class FakeProbe:
    def __init__(self):
        self.calls = 0

    def test(self, model, timeout=30.0):
        self.calls += 1
        return TestResult(model.key, True, ttft_ms=100.0, tested_at=time.time())


def mk(n, provider="fake"):
    return [ModelInfo(provider, f"m{i}:free") for i in range(n)]


# --- quota lag: /key is read before probing and can trail requests already sent -------------

class LaggingOpenRouter(FakeOpenRouter):
    """/key reports a ``used`` count that does not include requests already sent."""

    def __init__(self, models_payload, *, used, limit):
        super().__init__(models_payload, remaining=limit - used, limit=limit)


def test_local_probe_counter_caps_a_lagging_provider_counter(env, models_payload):
    tmp, cfg, _ = env
    utc_today = datetime.now(timezone.utc).date().isoformat()
    # this tool already sent 8 probes today, but /key still says only 2 were used
    (tmp / "cache.json").write_text(json.dumps({"daily": {"date": utc_today, "count": 8}}))
    api = LaggingOpenRouter(models_payload, used=2, limit=12)
    assert main(["-c", str(cfg), "test"], provider_factory=api.factory()) == 0
    assert api.chat_calls == 4  # 12 - 8 (local), not 10 (reported remaining)


def test_provider_counter_used_when_it_is_ahead(env, models_payload):
    tmp, cfg, _ = env
    utc_today = datetime.now(timezone.utc).date().isoformat()
    (tmp / "cache.json").write_text(json.dumps({"daily": {"date": utc_today, "count": 1}}))
    api = LaggingOpenRouter(models_payload, used=9, limit=12)  # other clients used the key too
    assert main(["-c", str(cfg), "test"], provider_factory=api.factory()) == 0
    assert api.chat_calls == 3


def test_rank_reports_quota_as_read_before_probing(env, models_payload, capsys):
    tmp, cfg, _ = env
    api = LaggingOpenRouter(models_payload, used=5, limit=50)
    assert main(["-c", str(cfg), "rank"], provider_factory=api.factory()) == 0
    out = capsys.readouterr().out
    probes = api.chat_calls
    assert probes > 0
    assert (
        f"used=5 remaining=45 (before this run's {probes} probe(s), about {45 - probes} left now; data may lag)"
        in out
    )

    assert main(["-c", str(cfg), "rank", "--json", "--no-probe"], provider_factory=api.factory()) == 0
    capsys.readouterr()
    assert main(["-c", str(cfg), "rank", "--json"], provider_factory=api.factory()) == 0
    quota = json.loads(capsys.readouterr().out)["quota"]["openrouter"]
    assert quota["probes_since_read"] == 0  # all fresh in the cache now: nothing probed
    assert quota["remaining_estimate"] == quota["daily_free_remaining"] == 45
    assert "lag" in quota["note"]


def test_quota_remaining_estimate():
    from freemodel_sync.models import QuotaInfo

    assert QuotaInfo().remaining_estimate is None
    assert QuotaInfo(daily_free_remaining=5, probes_since_read=3).remaining_estimate == 2
    assert QuotaInfo(daily_free_remaining=2, probes_since_read=9).remaining_estimate == 0
