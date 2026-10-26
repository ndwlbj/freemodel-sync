"""No silent success / adapter integrity (review items A4, E4, B7, B8, B10, B11,
C6, C9, C15, C19, D1, D2, D6). A3 is covered in test_yaml_comments.py."""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml
from conftest import make_selection

from freemodel_sync.adapters import get_adapter_class
from freemodel_sync.cli import EXIT_ACCOUNT_ERROR, main
from freemodel_sync.config import ConfigError, load_config
from freemodel_sync.flags import parse_bool
from freemodel_sync.models import ModelInfo, TestResult
from freemodel_sync.notify import notify_switch
from freemodel_sync.providers.openrouter import OpenRouterProvider, _parse_expiration_date
from freemodel_sync.ranking import RankWeights, filter_models, score_model
from freemodel_sync.tester import ResultCache, run_tests

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_snapshot.py"
_spec = importlib.util.spec_from_file_location("daily_snapshot_for_silent_success", _SCRIPT)
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

OK_STREAM = b'data: {"choices": [{"delta": {"content": "OK"}, "finish_reason": "stop"}]}\n\ndata: [DONE]\n\n'


class CountingProvider:
    name = "fake"

    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def test(self, model, timeout=30.0):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return TestResult(model.key, True, ttft_ms=10.0)


def models(n=3):
    return [ModelInfo("fake", f"v/m{i}:free") for i in range(n)]


def write_config(tmp_path, data):
    cfg = tmp_path / "config.yml"
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    return cfg


def openrouter_factory(models_payload, chat):
    def handler(request):
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json=models_payload)
        if path.endswith("/key"):
            return httpx.Response(200, json={"data": {"free_model_daily_requests": {"limit": 50, "remaining": 50}}})
        return chat(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return lambda name, **kw: OpenRouterProvider(api_key="k", client=client)


# -- shared bool parser (C9 + D6) ----------------------------------------------
@pytest.mark.parametrize("value", [True, 1, "true", "Yes", " ON ", "1"])
def test_parse_bool_true(value):
    assert parse_bool(value, name="x", default=False) is True


@pytest.mark.parametrize("value", [False, 0, "false", "No", "off", "0"])
def test_parse_bool_false(value):
    assert parse_bool(value, name="x", default=True) is False


def test_parse_bool_none_is_the_default():
    assert parse_bool(None, name="x", default=True) is True
    assert parse_bool(None, name="x", default=False) is False


@pytest.mark.parametrize("value", ["maybe", "", 2, 0.0, [], {}])
def test_parse_bool_rejects_other_values(value):
    with pytest.raises(ValueError, match="x must be true or false"):
        parse_bool(value, name="x", default=True)


# -- A4: max_tests below 1 ------------------------------------------------------
@pytest.mark.parametrize("value", [0, -1])
def test_config_rejects_max_tests_below_one(tmp_path, value):
    with pytest.raises(ConfigError, match="testing.max_tests"):
        load_config(write_config(tmp_path, {"testing": {"max_tests": value}}))


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_cli_rejects_max_tests_below_one(value, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["test", "--max-tests", value])
    assert exc.value.code == 2
    assert "--max-tests" in capsys.readouterr().err


@pytest.mark.parametrize("value", [0, -3])
def test_run_tests_says_why_nothing_was_probed(tmp_path, value):
    provider = CountingProvider()
    run = run_tests(provider, models(), cache=ResultCache(tmp_path / "c.json").load(), max_tests=value)
    assert provider.calls == 0 and run.probes == 0
    assert run.stop_reason == f"max_tests is {value}: no probe allowed"


# -- E4: snapshot --max-probes --------------------------------------------------
@pytest.mark.parametrize("value", ["0", "-1"])
def test_snapshot_rejects_max_probes_below_one(value):
    with pytest.raises(SystemExit):
        ds.build_parser().parse_args(["--out", "x", "--max-probes", value])


def test_snapshot_env_max_probes_is_validated(monkeypatch):
    monkeypatch.setenv("SNAPSHOT_MAX_PROBES", "0")
    with pytest.raises(SystemExit):
        ds.build_parser().parse_args(["--out", "x"])
    monkeypatch.setenv("SNAPSHOT_MAX_PROBES", "7")
    assert ds.build_parser().parse_args(["--out", "x"]).max_probes == 7


def test_snapshot_reserve_and_expiring_days_still_accept_zero():
    args = ds.build_parser().parse_args(["--out", "x", "--reserve", "0", "--expiring-days", "0"])
    assert args.reserve == 0 and args.expiring_days == 0


# -- B10 / B11 / C9: dsh adapter -----------------------------------------------
FLOW = "# my patch\n[{id: other, config: {a: 1}}, {id: agent-default-model, config: {provider: x, model: y}}]\n"


def test_dsh_refuses_a_flow_style_list(tmp_path, selection):
    p = tmp_path / "cordis.patch.yml"
    p.write_text(FLOW)
    with pytest.raises(ValueError, match="block-style"):
        get_adapter_class("dsh")(str(p)).apply(selection, backup=False)
    assert p.read_text() == FLOW


@pytest.mark.parametrize("text", ["[]\n", "", "# only a comment\n", "---\n"])
def test_dsh_still_writes_files_with_nothing_to_lose(tmp_path, selection, text):
    p = tmp_path / "cordis.patch.yml"
    p.write_text(text)
    get_adapter_class("dsh")(str(p)).apply(selection, backup=False)
    out = p.read_text()
    assert yaml.safe_load(out) == [
        {"id": "agent-default-model", "config": {"provider": "openrouter", "model": "vendor/a:free"}}
    ]
    if text.startswith("#"):
        assert out.startswith("# only a comment\n")  # kept, not dropped


def test_dsh_refuses_duplicate_managed_ids(tmp_path, selection):
    text = (
        "- id: agent-default-model\n  config: {provider: x, model: old1}\n"
        "- id: other\n  config: {}\n"
        "- id: agent-default-model\n  config: {provider: x, model: old2}\n"
    )
    p = tmp_path / "cordis.patch.yml"
    p.write_text(text)
    with pytest.raises(ValueError, match="2 entries have id 'agent-default-model'"):
        get_adapter_class("dsh")(str(p)).apply(selection, backup=False)
    assert p.read_text() == text


def test_dsh_duplicate_unmanaged_ids_are_left_alone(tmp_path, selection):
    text = "- id: other\n  config: {}\n- id: other\n  config: {}\n"
    p = tmp_path / "cordis.patch.yml"
    p.write_text(text)
    get_adapter_class("dsh")(str(p)).apply(selection, backup=False)
    assert p.read_text().startswith(text)


DSH_WITH_MODELS = """\
- id: llm-pi-ai
  config:
    providers:
      openrouter:
        models:
          - id: vendor/known:free
- id: agent-default-model
  config: {provider: openrouter, model: 'vendor/known:free'}
"""


@pytest.mark.parametrize("value", [None, True, "on", "yes"])
def test_dsh_check_model_on(tmp_path, value):
    p = tmp_path / "cordis.patch.yml"
    p.write_text(DSH_WITH_MODELS)
    with pytest.raises(ValueError, match="not in the models list"):
        get_adapter_class("dsh")(str(p), check_model=value).apply(make_selection(), backup=False)


@pytest.mark.parametrize("value", ["off", "OFF", 0, "no"])
def test_dsh_check_model_off(tmp_path, value):
    p = tmp_path / "cordis.patch.yml"
    p.write_text(DSH_WITH_MODELS)
    get_adapter_class("dsh")(str(p), check_model=value).apply(make_selection(), backup=False)
    assert yaml.safe_load(p.read_text())[1]["config"]["model"] == "vendor/a:free"


def test_dsh_check_model_rejects_an_unclear_value(tmp_path):
    p = tmp_path / "cordis.patch.yml"
    p.write_text(DSH_WITH_MODELS)
    with pytest.raises(ValueError, match="check_model must be true or false"):
        get_adapter_class("dsh")(str(p), check_model="sometimes").apply(make_selection(), backup=False)
    assert p.read_text() == DSH_WITH_MODELS


# -- C15: creating a missing target ---------------------------------------------
def test_missing_target_file_is_created_with_a_warning(tmp_path, selection, caplog):
    p = tmp_path / "new" / "app.env"
    with caplog.at_level(logging.WARNING):
        result = get_adapter_class("openai-env")(str(p)).apply(selection, dry_run=True)
    assert result.changed and not p.exists()
    assert "does not exist; it would be created" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        get_adapter_class("openai-env")(str(p)).apply(selection)
    assert p.exists() and "does not exist; creating it" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        get_adapter_class("openai-env")(str(p)).apply(selection)
    assert "does not exist" not in caplog.text


# -- B7 / D6: notifications -----------------------------------------------------
def _never_called_client():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_configured_channel_with_missing_env_warns(monkeypatch, caplog):
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "FREEMODEL_SYNC_WEBHOOK_URL", "MY_HOOK"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level(logging.WARNING):
        sent = notify_switch(
            None, make_selection(), telegram={}, webhook={"url_env": "MY_HOOK"}, client=_never_called_client()
        )
    assert sent == []
    assert "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID" in caplog.text
    assert "MY_HOOK is not set" in caplog.text


@pytest.mark.parametrize("value", [False, "false", "off", "no", 0])
def test_disabled_channels_send_nothing(monkeypatch, caplog, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    with caplog.at_level(logging.WARNING):
        sent = notify_switch(
            None,
            make_selection(),
            telegram={"enabled": value},
            webhook={"enabled": value, "url": "https://hook.invalid/x"},
            client=_never_called_client(),
        )
    assert sent == [] and caplog.text == ""


def test_invalid_enabled_value_disables_the_channel_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        sent = notify_switch(
            None,
            make_selection(),
            webhook={"enabled": "nope", "url": "https://x.invalid"},
            client=_never_called_client(),
        )
    assert sent == [] and "notify.webhook.enabled must be true or false" in caplog.text


def test_config_normalizes_notify_enabled(tmp_path):
    cfg = load_config(write_config(tmp_path, {"notify": {"telegram": {"enabled": "false"}, "webhook": {}}}))
    assert cfg.notify.telegram == {"enabled": False}
    with pytest.raises(ConfigError, match="notify.webhook.enabled"):
        load_config(write_config(tmp_path, {"notify": {"webhook": {"enabled": "perhaps"}}}))


def test_empty_notify_section_is_allowed(tmp_path):
    cfg = tmp_path / "config.yml"
    cfg.write_text("notify:\n  # telegram:\n  #   bot_token_env: X\n")
    assert load_config(cfg).notify.telegram is None


# -- D1: unknown keys inside sections --------------------------------------------
def test_unknown_section_keys_warn(tmp_path, caplog):
    data = {
        "providers": {"openrouter": {"probe_max_tokens": 8}},  # provider options are open
        "testing": {"max_test": 3},
        "ranking": {"weights": {"latnecy": 1}},
        "notify": {"telegram": {"chat_env": "X"}},
        "targets": [{"adapter": "dsh", "path": "x.yml", "option": {}}],
        "extra_top": 1,
    }
    with caplog.at_level(logging.WARNING):
        load_config(write_config(tmp_path, data))
    text = caplog.text
    for key in ("extra_top", "testing.max_test", "ranking.weights.latnecy", "notify.telegram.chat_env"):
        assert key in text
    assert "targets[0].option" in text
    assert "probe_max_tokens" not in text


def test_unknown_section_keys_are_errors_in_strict_mode(tmp_path):
    with pytest.raises(ConfigError, match=r"filters\.min_ctx"):
        load_config(write_config(tmp_path, {"filters": {"min_ctx": 1}}), strict=True)


def test_known_keys_do_not_warn(tmp_path, caplog):
    example = Path(__file__).resolve().parents[1] / "examples" / "config.example.yml"
    with caplog.at_level(logging.WARNING):
        load_config(example)
    assert "unknown config key" not in caplog.text


# -- D2: rank exit code -----------------------------------------------------------
@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_rank_returns_the_account_error_exit_code(tmp_path, models_payload, capsys, extra):
    platform_429 = {"error": {"code": 429, "message": "free-models-per-day", "metadata": {}}}
    factory = openrouter_factory(models_payload, lambda request: httpx.Response(429, json=platform_429))
    cfg = write_config(
        tmp_path,
        {"testing": {"cache_path": str(tmp_path / "c.json"), "reserve_requests": 0}, "state_path": str(tmp_path / "s")},
    )
    assert main(["-c", str(cfg), "rank", *extra], provider_factory=factory) == EXIT_ACCOUNT_ERROR
    assert main(["-c", str(cfg), "test"], provider_factory=factory) == EXIT_ACCOUNT_ERROR


def test_rank_still_returns_zero_normally(tmp_path, models_payload):
    factory = openrouter_factory(models_payload, lambda request: httpx.Response(200, content=OK_STREAM))
    cfg = write_config(
        tmp_path,
        {"testing": {"cache_path": str(tmp_path / "c.json"), "reserve_requests": 0}, "state_path": str(tmp_path / "s")},
    )
    assert main(["-c", str(cfg), "rank", "--json"], provider_factory=factory) == 0


# -- B8: notify-only runs ------------------------------------------------------------
def test_sync_without_targets_says_what_it_records(tmp_path, models_payload, capsys):
    factory = openrouter_factory(models_payload, lambda request: httpx.Response(200, content=OK_STREAM))
    state = tmp_path / "state.json"
    cfg = write_config(
        tmp_path, {"testing": {"cache_path": str(tmp_path / "c.json"), "reserve_requests": 0}, "state_path": str(state)}
    )
    assert main(["-c", str(cfg), "sync", "--no-notify"], provider_factory=factory) == 0
    assert "no targets configured; nothing to write" in capsys.readouterr().err
    assert json.loads(state.read_text())["primary"]


# -- C6: expired models -----------------------------------------------------------
def test_expired_models_are_dropped_even_without_the_expiry_filter():
    today = date(2026, 10, 10)
    models_ = [
        ModelInfo("p", "a/expired:free", expiration_date=date(2026, 10, 5)),
        ModelInfo("p", "a/today:free", expiration_date=today),
        ModelInfo("p", "a/later:free", expiration_date=date(2026, 12, 1)),
    ]
    kept = [m.id for m in filter_models(models_, exclude_expiring_within_days=None, today=today)]
    assert kept == ["a/today:free", "a/later:free"]
    kept = [m.id for m in filter_models(models_, exclude_expiring_within_days=None, exclude_expired=False, today=today)]
    assert kept == ["a/expired:free", "a/today:free", "a/later:free"]


def test_expired_model_reason_is_not_negative():
    model = ModelInfo("p", "a/expired:free", expiration_date=date(2026, 10, 5))
    _score, reasons = score_model(model, None, RankWeights(), today=date(2026, 10, 10))
    assert "expired 5 day(s) ago" in reasons
    assert not any("-5" in reason for reason in reasons)


# -- C19: untested branches -------------------------------------------------------
def test_provider_exception_becomes_a_counted_transient_failure(tmp_path):
    provider = CountingProvider(error=RuntimeError("boom"))
    cache = ResultCache(tmp_path / "c.json").load()
    run = run_tests(provider, models(2), cache=cache, max_tests=5)
    assert provider.calls == 2 and run.probes == 2
    result = run["fake|v/m0:free"]
    assert result.ok is False and result.failure_kind == "transient"
    assert result.error == "RuntimeError: boom"
    assert run.stop_reason is None and not run.account_problem
    assert cache.get("fake|v/m0:free", 3600, 1800) is not None  # cached for the transient TTL


def test_legacy_cache_entry_without_failure_kind_is_a_model_failure():
    legacy = {"key": "p|m", "ok": False, "error": "old", "tested_at": "12.5"}
    result = TestResult.from_dict(legacy)
    assert result.failure_kind == "model" and result.tested_at == 12.5 and result.cached is False
    assert TestResult.from_dict({"key": "p|m", "ok": True}).failure_kind is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-30T00:00:00Z", date(2026, 11, 30)),
        ("2026-11-30T23:30:00.000Z", date(2026, 11, 30)),
        ("2026-11-30", date(2026, 11, 30)),
        ("2026-11-30T08:00:00+08:00", date(2026, 11, 30)),
        ("soon", None),
        ("", None),
        (None, None),
    ],
)
def test_expiration_date_parsing(raw, expected):
    assert _parse_expiration_date(raw) == expected
