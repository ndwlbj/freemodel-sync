"""Regression tests: -v must never print secrets (review P1-1)."""

from __future__ import annotations

import logging
import time

import httpx
import pytest
import yaml

from freemodel_sync.cli import RedactingFilter, main
from freemodel_sync.models import ModelInfo, QuotaInfo, TestResult

TOKEN = "123456:TEST-telegram-token-value"


class Stub:
    api_key = "test-key"

    def discover(self):
        return [ModelInfo("openrouter", "a/b:free", context_length=65536)]

    def test(self, model, timeout=30.0):
        return TestResult(model.key, True, ttft_ms=10.0, tested_at=time.time())

    def quota(self):
        return QuotaInfo(daily_free_limit=50, daily_free_remaining=50)


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    logging.getLogger().setLevel(logging.WARNING)


@pytest.mark.parametrize("flags", [["-v"], ["-v", "--debug-http"]])
def test_verbose_sync_does_not_log_telegram_token(tmp_path, monkeypatch, capsys, flags):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    sent = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    real_client = httpx.Client
    monkeypatch.setattr(
        "freemodel_sync.notify.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler)),
    )
    cfg = tmp_path / "c.yml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "testing": {"cache_path": str(tmp_path / "cache.json")},
                "state_path": str(tmp_path / "state.json"),
                "notify": {"telegram": {}},
            }
        )
    )
    assert main([*flags, "-c", str(cfg), "sync"], provider_factory=lambda name, **kw: Stub()) == 0
    assert sent and TOKEN in sent[0]  # the request itself still carries the token
    err = capsys.readouterr().err
    assert TOKEN not in err
    if "--debug-http" in flags:
        assert "api.telegram.org/bot<redacted>" in err


def test_redacting_filter_patterns():
    text = RedactingFilter.redact(f"POST https://api.telegram.org/bot{TOKEN}/sendMessage Authorization: Bearer abc.def")
    assert TOKEN not in text and "abc.def" not in text
    assert "bot<redacted>/sendMessage" in text


def test_redacting_formatter_covers_tracebacks(capsys):
    """B15: a secret inside an exception (exc_info) is redacted, not only the message."""

    from freemodel_sync import cli

    cli._configure_logging(verbose=True)  # replaces any handler left by an earlier main() call
    try:
        try:
            raise RuntimeError(f"POST https://api.telegram.org/bot{TOKEN}/sendMessage failed")
        except RuntimeError:
            logging.getLogger("freemodel_sync.test").debug("send failed", exc_info=True)
            logging.getLogger("freemodel_sync.test").debug("stack", stack_info=True)
    finally:
        logging.getLogger().removeHandler(cli._LOG_HANDLER)
        cli._LOG_HANDLER = None
    err = capsys.readouterr().err
    assert "RuntimeError" in err and "send failed" in err
    assert TOKEN not in err
    assert "api.telegram.org/bot<redacted>/sendMessage" in err


def test_redacting_formatter_redacts_cached_exc_text():
    import sys

    from freemodel_sync.cli import RedactingFormatter

    try:
        raise ValueError(f"Bearer {TOKEN}")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    out = RedactingFormatter("%(message)s").format(record)
    assert TOKEN not in out and TOKEN not in (record.exc_text or "")
