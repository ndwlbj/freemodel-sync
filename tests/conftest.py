from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from freemodel_sync.models import ModelInfo, RankedModel, Selection, TestResult

FIXTURES = Path(__file__).parent / "fixtures"

#: environment variables with real credentials or endpoints; never visible to tests
_REAL_ENV = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "GROQ_PLAN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "FREEMODEL_SYNC_WEBHOOK_URL",
    "FREEMODEL_SYNC_CONFIG",
    "GITHUB_TOKEN",
)


class NetworkBlockedError(RuntimeError):
    """A test tried to open a real network connection."""


def _blocked(*args, **kwargs):
    raise NetworkBlockedError(
        "tests must not use the network: inject an httpx.MockTransport (or mark the test allow_network)"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "allow_network: let this test open real network connections")


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests never reach the network and never see real API keys (F6).

    Internet sockets cannot connect and DNS lookups fail; ``httpx.MockTransport``
    does not use sockets, so mocked HTTP keeps working. AF_UNIX sockets stay usable.
    """

    for name in _REAL_ENV:
        monkeypatch.delenv(name, raising=False)
    if request.node.get_closest_marker("allow_network"):
        return
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _blocked()
        return real_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _blocked()
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture
def models_payload():
    return json.loads((FIXTURES / "openrouter_models.json").read_text(encoding="utf-8"))


def make_selection(primary="vendor/a:free", fallbacks=("vendor/b:free", "vendor/c:free"), provider="openrouter"):
    def rm(mid):
        return RankedModel(
            ModelInfo(provider, mid),
            100.0,
            TestResult(key=f"{provider}|{mid}", ok=True, ttft_ms=100.0),
        )

    return Selection(primary=rm(primary), fallbacks=[rm(f) for f in fallbacks])


@pytest.fixture
def selection():
    return make_selection()
