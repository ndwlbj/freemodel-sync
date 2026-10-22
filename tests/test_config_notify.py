from __future__ import annotations

import json

import httpx
import pytest
from conftest import make_selection

from freemodel_sync.config import ConfigError, load_config
from freemodel_sync.notify import build_message, notify_switch


def test_defaults_when_default_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FREEMODEL_SYNC_CONFIG", str(tmp_path / "missing.yml"))
    cfg = load_config()
    assert cfg.enabled_providers() == ["openrouter"]
    assert cfg.testing.max_tests == 5
    assert cfg.testing.daily_free_limit is None
    assert cfg.filters.exclude_expiring_within_days == 3
    assert cfg.targets == []


def test_load_full_config(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text(
        """
filters: {require_tools: true, min_context: 32000, include: ["*:free"]}
testing: {max_tests: 2, cache_path: ~/x/results.json, daily_free_limit: 50}
ranking: {weights: {tools: 0}, fallback_count: 1}
targets:
  - adapter: dsh
    path: ~/somewhere/bot-model.yml
    options: {provider_map: {openrouter: my-openrouter}}
notify:
  webhook: {url_env: MY_HOOK}
"""
    )
    cfg = load_config(p)
    assert cfg.filters.require_tools is True and cfg.filters.min_context == 32000
    assert cfg.testing.max_tests == 2 and cfg.testing.daily_free_limit == 50
    assert "~" not in str(cfg.testing.cache_path)
    assert cfg.ranking.weights.tools == 0 and cfg.ranking.weights.availability == 100
    assert cfg.targets[0].adapter == "dsh"
    assert cfg.targets[0].options["provider_map"] == {"openrouter": "my-openrouter"}
    assert cfg.notify.webhook == {"url_env": "MY_HOOK"}


@pytest.mark.parametrize(
    "text",
    [
        "targets: [{adapter: nope, path: x}]",
        "testing: {max_tests: -1}",
        "filters: {require_tools: maybe}",
        "- not a mapping",
        "filters: [",
    ],
)
def test_invalid_config(tmp_path, text):
    p = tmp_path / "c.yml"
    p.write_text(text)
    with pytest.raises(ConfigError):
        load_config(p)


def test_explicit_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yml")


def test_notify_webhook_and_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("FREEMODEL_SYNC_WEBHOOK_URL", "https://hooks.example.invalid/x")
    sent = []

    def handler(request):
        sent.append((request.url.host, json.loads(request.content)))
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sel = make_selection()
    channels = notify_switch("openrouter|old:free", sel, telegram={}, webhook={}, client=client)
    assert channels == ["telegram", "webhook"]
    assert sent[0][0] == "api.telegram.org" and sent[0][1]["chat_id"] == "42"
    assert sent[1][1]["event"] == "primary_changed"
    assert sent[1][1]["new"] == "openrouter|vendor/a:free"
    assert sent[1][1]["fallbacks"] == ["vendor/b:free", "vendor/c:free"]


def test_notify_never_raises_and_hides_secrets(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def handler(request):
        raise httpx.ConnectError("boom " + str(request.url), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert notify_switch(None, make_selection(), telegram={}, client=client) == []
    assert "super-secret-token" not in caplog.text


def test_notify_skips_without_env_or_in_dry_run(monkeypatch):
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "FREEMODEL_SYNC_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)

    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert notify_switch(None, make_selection(), telegram={}, webhook={}, client=client) == []
    assert notify_switch(None, make_selection(), webhook={"url": "https://x.invalid"}, dry_run=True) == []


def test_build_message():
    msg = build_message(None, make_selection())
    assert msg.startswith("freemodel-sync: primary model changed: none -> openrouter|vendor/a:free")


def test_example_config_is_valid():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / "examples" / "config.example.yml"
    cfg = load_config(example)
    assert {t.adapter for t in cfg.targets} == {"openai-env", "openai-yaml", "dsh", "astrbot"}


def test_inline_webhook_url_warns_and_checks_permissions(tmp_path, caplog):
    """Review P2-5: a tokenized webhook URL in a group/world-readable config file."""
    import os

    from freemodel_sync.config import load_config

    cfg = tmp_path / "config.yml"
    cfg.write_text("notify:\n  webhook:\n    url: https://hooks.example.com/T0KEN\n")
    os.chmod(cfg, 0o644)
    with caplog.at_level("WARNING"):
        load_config(cfg)
    assert "prefer notify.webhook.url_env" in caplog.text
    assert "chmod 600" in caplog.text and "T0KEN" not in caplog.text

    caplog.clear()
    os.chmod(cfg, 0o600)
    with caplog.at_level("WARNING"):
        load_config(cfg)
    assert "url_env" in caplog.text and "chmod" not in caplog.text

    caplog.clear()
    cfg.write_text("notify:\n  webhook:\n    url_env: MY_HOOK\n")
    os.chmod(cfg, 0o644)
    with caplog.at_level("WARNING"):
        load_config(cfg)
    assert caplog.text == ""
