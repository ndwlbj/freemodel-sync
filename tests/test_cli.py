from __future__ import annotations

import json
import time

import pytest
import yaml

from freemodel_sync import __version__
from freemodel_sync.cli import main
from freemodel_sync.models import ModelInfo, QuotaInfo, TestResult


class StubProvider:
    def __init__(self, ok_ids, quota_limit=50, api_key="test-key"):
        self.api_key = api_key
        self.ok_ids = set(ok_ids)
        self.quota_limit = quota_limit
        self.tested = []

    def discover(self):
        return [
            ModelInfo("openrouter", "big/tools:free", context_length=262144, supports_tools=True),
            ModelInfo("openrouter", "mid/model:free", context_length=131072, supports_tools=True),
            ModelInfo("openrouter", "small/model:free", context_length=8192),
        ]

    def test(self, model, timeout=30.0):
        self.tested.append(model.id)
        ok = model.id in self.ok_ids
        return TestResult(model.key, ok, ttft_ms=250.0 if ok else None, error=None if ok else "503",
                          tested_at=time.time())

    def quota(self):
        self.quota_calls = getattr(self, "quota_calls", 0) + 1
        return QuotaInfo(is_free_tier=True, daily_free_limit=self.quota_limit)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    target = tmp_path / "bot-model.yml"
    target.write_text("- id: agent-default-model\n  config: {provider: x, model: 'old'}\n")
    cfg = tmp_path / "config.yml"
    cfg.write_text(yaml.safe_dump({
        "testing": {"cache_path": str(tmp_path / "cache.json"), "max_tests": 5},
        "state_path": str(tmp_path / "state.json"),
        "ranking": {"fallback_count": 2},
        "targets": [{"adapter": "dsh", "path": str(target)}],
    }))
    return tmp_path, cfg, target


def run(cfg, provider, *args):
    return main(["-c", str(cfg), *args], provider_factory=lambda name, **kw: provider)


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_list_commands(capsys, setup):
    _, cfg, _ = setup
    assert main(["-c", str(cfg), "adapters"]) == 0
    assert "dsh" in capsys.readouterr().out
    assert main(["-c", str(cfg), "providers"]) == 0
    assert "openrouter" in capsys.readouterr().out


def test_discover_json(capsys, setup):
    _, cfg, _ = setup
    assert run(cfg, StubProvider([]), "discover", "--json") == 0
    data = json.loads(capsys.readouterr().out)
    assert [m["id"] for m in data][0] == "big/tools:free"


def test_rank_json_and_output(capsys, setup):
    tmp, cfg, _ = setup
    out = tmp / "ranking.json"
    provider = StubProvider({"mid/model:free", "small/model:free"})
    assert run(cfg, provider, "rank", "--json", "--output", str(out)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selection"]["primary"] == "mid/model:free"
    assert payload["quota"]["daily_free_limit"] == 50
    assert json.loads(out.read_text())["ranking"][0]["id"] == "mid/model:free"
    # the most promising model (largest context + tools) is probed first
    assert provider.tested[0] == "big/tools:free"


def test_sync_dry_run_then_write_then_idempotent(capsys, setup, monkeypatch):
    tmp, cfg, target = setup
    calls = []
    monkeypatch.setattr("freemodel_sync.cli.notify_switch", lambda *a, **k: calls.append(a) or ["webhook"])
    provider = StubProvider({"big/tools:free", "mid/model:free"})

    assert run(cfg, provider, "sync", "--dry-run", "--probe") == 0
    out = capsys.readouterr().out
    assert "would update" in out and "+  config: {provider: openrouter, model: 'big/tools:free'}" in out
    assert "old" in target.read_text() and not (tmp / "state.json").exists() and calls == []

    assert run(cfg, provider, "sync") == 0
    assert "model: 'big/tools:free'" in target.read_text()
    assert json.loads((tmp / "state.json").read_text())["primary"] == "openrouter|big/tools:free"
    assert len(calls) == 1 and list(tmp.glob("bot-model.yml.bak-*"))

    capsys.readouterr()
    assert run(cfg, provider, "sync") == 0  # cached results, unchanged file, no new notification
    assert "unchanged" in capsys.readouterr().out
    assert len(calls) == 1


def test_sync_no_usable_model_writes_nothing(capsys, setup):
    tmp, cfg, target = setup
    before = target.read_text()
    assert run(cfg, StubProvider(set()), "sync") == 2
    assert target.read_text() == before
    assert not (tmp / "state.json").exists()


def test_daily_budget_limits_probes(setup):
    _, cfg, _ = setup
    provider = StubProvider({"big/tools:free"}, quota_limit=12)  # 12 - reserve 10 -> 2 probes max
    run(cfg, provider, "test")
    assert len(provider.tested) == 2


def test_bad_config_returns_1(tmp_path, capsys):
    p = tmp_path / "c.yml"
    p.write_text("targets: [{adapter: nope, path: x}]")
    assert main(["-c", str(p), "discover"]) == 1
    assert "unknown adapter" in capsys.readouterr().err


def test_untested_fallbacks_are_opt_in_and_flagged(capsys, setup):
    """Review P1-4: untested models only become fallbacks when explicitly allowed."""
    tmp, cfg, target = setup
    data = yaml.safe_load(cfg.read_text())
    data["testing"]["max_tests"] = 1  # only big/tools gets probed
    cfg.write_text(yaml.safe_dump(data))
    provider = StubProvider({"big/tools:free"})
    assert run(cfg, provider, "rank", "--json") == 0
    sel = json.loads(capsys.readouterr().out)["selection"]
    assert sel["fallbacks"] == [] and sel["untested_fallbacks"] == []

    data["ranking"]["fallbacks_allow_untested"] = True
    cfg.write_text(yaml.safe_dump(data))
    assert run(cfg, provider, "sync", "--no-notify") == 0
    out = capsys.readouterr().out
    assert "(untested)" in out


def test_dry_run_is_zero_cost(capsys, setup):
    """Review P1-6: --dry-run sends no probes and writes no cache/state/targets."""
    tmp, cfg, target = setup
    before = target.read_text()
    provider = StubProvider({"big/tools:free"}, api_key=None)  # no key needed either
    assert run(cfg, provider, "sync", "--dry-run") == 2
    assert provider.tested == [] and getattr(provider, "quota_calls", 0) == 0
    assert "cached probe results only" in capsys.readouterr().err
    assert not (tmp / "cache.json").exists() and not (tmp / "state.json").exists()

    # populate the cache with a real (mocked) probe round, then dry-run again
    keyed = StubProvider({"big/tools:free", "mid/model:free"})
    assert run(cfg, keyed, "test") == 0
    cache_before = (tmp / "cache.json").read_bytes()
    provider = StubProvider(set(), api_key=None)
    assert run(cfg, provider, "sync", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would update" in out and "big/tools:free" in out
    assert provider.tested == [] and getattr(provider, "quota_calls", 0) == 0
    assert (tmp / "cache.json").read_bytes() == cache_before
    assert target.read_text() == before and not (tmp / "state.json").exists()


def test_no_probe_sync_writes_from_cache_only(capsys, setup):
    tmp, cfg, target = setup
    assert run(cfg, StubProvider({"mid/model:free"}), "test") == 0
    provider = StubProvider(set(), api_key=None)
    assert run(cfg, provider, "sync", "--no-probe", "--no-notify") == 0
    assert provider.tested == []
    assert "model: 'mid/model:free'" in target.read_text()


def test_rank_no_probe(capsys, setup):
    _, cfg, _ = setup
    provider = StubProvider({"big/tools:free"}, api_key=None)
    assert run(cfg, provider, "rank", "--no-probe", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selection"] is None and provider.tested == []
