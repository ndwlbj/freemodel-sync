"""Review P2-3: every enabled provider feeds one ranking (all HTTP is stubbed)."""

import json
import time

import pytest
import yaml

from freemodel_sync.cli import main
from freemodel_sync.config import ConfigError, load_config
from freemodel_sync.models import ModelInfo, TestResult


class Stub:
    def __init__(self, name, models, ok, api_key, fail=None):
        self.name, self.api_key = name, api_key
        self._models, self.ok, self.fail = models, set(ok), fail
        self.tested = []

    def discover(self):
        return [ModelInfo(self.name, mid, context_length=ctx, supports_tools=tools)
                for mid, ctx, tools in self._models]

    def test(self, model, timeout=30.0):
        self.tested.append(model.id)
        if self.fail:
            return TestResult(model.key, False, error="rate limited", status_code=429,
                              failure_kind="account", retry_after_s=600, tested_at=time.time())
        ok = model.id in self.ok
        return TestResult(model.key, ok, ttft_ms=100.0 if ok else None,
                          error=None if ok else "503", tested_at=time.time())

    def quota(self):
        return None


OR_MODELS = [("or/small:free", 8192, False), ("or/mid:free", 32768, False)]
GQ_MODELS = [("llama-big", 131072, True), ("llama-small", 8192, False)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    for var in ("OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    target = tmp_path / "bot.env"
    target.write_text("OPENAI_MODEL=old\n")
    stubs = {}

    def write(providers, targets=None, **extra):
        cfg = tmp_path / "config.yml"
        cfg.write_text(yaml.safe_dump({
            "providers": providers,
            "testing": {"cache_path": str(tmp_path / "cache.json"), "max_tests": 5},
            "state_path": str(tmp_path / "state.json"),
            "ranking": {"fallback_count": 2},
            "targets": targets if targets is not None else [{"adapter": "openai-env", "path": str(target)}],
            **extra,
        }, sort_keys=False))
        return cfg

    def factory(name, api_key=None, **options):
        spec = stubs[name]
        stub = Stub(name, spec["models"], spec.get("ok", ()), api_key, spec.get("fail"))
        spec["instance"] = stub
        return stub

    def run(cfg, *args):
        return main(["-c", str(cfg), *args], provider_factory=factory)

    return tmp_path, target, stubs, write, run


def test_all_enabled_providers_merge_into_one_ranking(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.setenv("GROQ_API_KEY", "fake-gq")
    stubs["openrouter"] = {"models": OR_MODELS, "ok": {"or/small:free", "or/mid:free"}}
    stubs["groq"] = {"models": GQ_MODELS, "ok": {"llama-big", "llama-small"}}
    cfg = write({"openrouter": {}, "groq": {"plan": "free"}},
                targets=[{"adapter": "openai-env", "path": str(target), "options": {"providers": ["groq"]}}])

    assert run(cfg, "rank", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["providers"] == ["openrouter", "groq"]
    providers = {item["provider"] for item in payload["ranking"]}
    assert providers == {"openrouter", "groq"}
    sel = payload["selection"]
    assert sel["provider"] == "groq" and sel["primary"] == "llama-big"
    assert sel["fallbacks"] == ["llama-small"]  # never a fallback from another provider
    # each provider got its own key, never the other one's
    assert stubs["openrouter"]["instance"].api_key == "fake-or"
    assert stubs["groq"]["instance"].api_key == "fake-gq"
    # separate caches: the first provider keeps testing.cache_path
    assert (tmp / "cache.json").exists() and (tmp / "cache.groq.json").exists()
    assert set(json.loads((tmp / "cache.groq.json").read_text())) >= {"groq|llama-big"}
    assert not any(k.startswith("groq|") for k in json.loads((tmp / "cache.json").read_text()))

    assert run(cfg, "discover") == 0
    out = capsys.readouterr().out
    assert "2 from openrouter, 2 from groq" in out


def test_account_error_stops_only_that_provider(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.setenv("GROQ_API_KEY", "fake-gq")
    stubs["openrouter"] = {"models": OR_MODELS, "ok": {"or/mid:free"}}
    stubs["groq"] = {"models": GQ_MODELS, "fail": True}
    cfg = write({"groq": {"plan": "free"}, "openrouter": {}},
                targets=[{"adapter": "openai-env", "path": str(target), "options": {"providers": ["openrouter"]}}])
    assert run(cfg, "sync", "--no-notify") == 0
    err = capsys.readouterr().err
    assert "groq: account/quota error" in err
    assert stubs["groq"]["instance"].tested == ["llama-big"]  # one request, then stop
    assert len(stubs["openrouter"]["instance"].tested) == 2
    assert "OPENAI_MODEL=or/mid:free" in target.read_text()
    assert "OPENAI_BASE_URL=https://openrouter.ai/api/v1" in target.read_text()
    groq_cache = json.loads((tmp / "cache.json").read_text())  # groq is first here
    assert groq_cache["blocked_until"] > time.time() + 300
    assert not any(k.startswith("groq|") for k in groq_cache if "|" in k)


def test_target_providers_restricts_selection(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.setenv("GROQ_API_KEY", "fake-gq")
    stubs["openrouter"] = {"models": OR_MODELS, "ok": {"or/small:free"}}
    stubs["groq"] = {"models": GQ_MODELS, "ok": {"llama-big"}}
    other = tmp / "other.env"
    other.write_text("")
    cfg = write({"openrouter": {}, "groq": {"plan": "free"}}, targets=[
        {"adapter": "openai-env", "path": str(target), "options": {"providers": ["openrouter"]}},
        {"adapter": "openai-env", "path": str(other), "options": {"providers": ["groq"]}},
    ])
    assert run(cfg, "sync", "--no-notify") == 0
    assert "OPENAI_MODEL=or/small:free" in target.read_text()
    assert "OPENAI_MODEL=llama-big" in other.read_text()
    assert "api.groq.com" in other.read_text()
    state = json.loads((tmp / "state.json").read_text())
    assert state["primary"] == "groq|llama-big"
    assert state["targets"] == {f"openai-env:{target}": "openrouter|or/small:free",
                                f"openai-env:{other}": "groq|llama-big"}


def test_target_with_no_usable_model_fails_without_advancing_state(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.setenv("GROQ_API_KEY", "fake-gq")
    stubs["openrouter"] = {"models": OR_MODELS, "ok": set()}
    stubs["groq"] = {"models": GQ_MODELS, "ok": {"llama-big"}}
    cfg = write({"openrouter": {}, "groq": {"plan": "free"}},
                targets=[{"adapter": "openai-env", "path": str(target), "options": {"providers": ["openrouter"]}}])
    assert run(cfg, "sync", "--no-notify") == 1
    assert "no usable model from its providers openrouter" in capsys.readouterr().err
    assert target.read_text() == "OPENAI_MODEL=old\n"
    assert not (tmp / "state.json").exists()


def test_openrouter_can_be_disabled_or_omitted(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    monkeypatch.setenv("GROQ_API_KEY", "fake-gq")
    stubs["groq"] = {"models": GQ_MODELS, "ok": {"llama-small"}}
    stubs["openrouter"] = {"models": OR_MODELS, "ok": {"or/mid:free"}}
    for providers in ({"openrouter": {"enabled": False}, "groq": {"plan": "free"}}, {"groq": {"plan": "free"}}):
        cfg = write(providers)
        assert load_config(cfg).enabled_providers() == ["groq"]
        stubs["openrouter"].pop("instance", None)
        assert run(cfg, "rank", "--json") == 0
        assert json.loads(capsys.readouterr().out)["providers"] == ["groq"]
        assert "instance" not in stubs["openrouter"]


def test_default_providers_is_openrouter_only(tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("filters: {min_context: 0}\n")
    config = load_config(cfg)
    assert config.enabled_providers() == ["openrouter"]
    assert config.providers["openrouter"].api_key_env == "OPENROUTER_API_KEY"


def test_each_provider_defaults_to_its_own_key_env(tmp_path):
    cfg = tmp_path / "c.yml"
    cfg.write_text("providers:\n  groq: {plan: free}\n  openrouter: {api_key_env: MY_OR_KEY}\n")
    config = load_config(cfg)
    assert config.providers["groq"].api_key_env == "GROQ_API_KEY"
    assert config.providers["openrouter"].api_key_env == "MY_OR_KEY"


def test_one_missing_key_is_skipped_all_missing_is_an_error(capsys, env, monkeypatch):
    tmp, target, stubs, write, run = env
    stubs["openrouter"] = {"models": OR_MODELS, "ok": {"or/mid:free"}}
    stubs["groq"] = {"models": GQ_MODELS, "ok": {"llama-big"}}
    cfg = write({"openrouter": {}, "groq": {"plan": "free"}},
                targets=[{"adapter": "openai-env", "path": str(target), "options": {"providers": ["openrouter"]}}])
    assert run(cfg, "test") == 1
    assert "no enabled provider has an API key set" in capsys.readouterr().err
    assert stubs["groq"]["instance"].tested == [] and stubs["openrouter"]["instance"].tested == []

    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    assert run(cfg, "test") == 0
    assert "not probing groq: GROQ_API_KEY is not set" in capsys.readouterr().err
    assert stubs["groq"]["instance"].tested == []


@pytest.mark.parametrize("providers, targets, message", [
    ({"nope": {}}, [], "unknown provider 'nope'"),
    ({"openrouter": {}}, [{"adapter": "openai-env", "path": "x", "options": {"providers": ["groq"]}}],
     "not in the providers section: groq"),
    ({"openrouter": {}}, [{"adapter": "openai-env", "path": "x", "options": {"providers": "openrouter"}}],
     "non-empty list"),
])
def test_provider_config_errors(tmp_path, providers, targets, message):
    cfg = tmp_path / "c.yml"
    cfg.write_text(yaml.safe_dump({"providers": providers, "targets": targets}))
    with pytest.raises(ConfigError, match=message):
        load_config(cfg)


def test_warns_when_target_could_switch_provider(tmp_path, caplog):
    cfg = tmp_path / "c.yml"
    cfg.write_text(yaml.safe_dump({
        "providers": {"openrouter": {}, "groq": {"plan": "free"}},
        "targets": [{"adapter": "openai-env", "path": str(tmp_path / "a.env")},
                    {"adapter": "openai-env", "path": str(tmp_path / "b.env"),
                     "options": {"providers": ["groq"]}}],
    }))
    with caplog.at_level("WARNING"):
        load_config(cfg)
    assert caplog.text.count("has no options.providers") == 1 and "a.env" in caplog.text
