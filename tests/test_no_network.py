"""The autouse guard in conftest.py keeps tests offline (F6)."""

from __future__ import annotations

import os
import socket

import httpx
import pytest

BLOCKED = "tests must not use the network"


def test_real_http_request_is_blocked():
    with pytest.raises(Exception) as exc:
        httpx.get("https://openrouter.ai/api/v1/models", timeout=5)
    chain = [exc.value, exc.value.__cause__, exc.value.__context__]
    assert any(BLOCKED in str(e) for e in chain if e is not None)


def test_raw_socket_connect_is_blocked():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match=BLOCKED):
            sock.connect(("127.0.0.1", 9))
        with pytest.raises(RuntimeError, match=BLOCKED):
            sock.connect_ex(("127.0.0.1", 9))
    finally:
        sock.close()
    with pytest.raises(RuntimeError, match=BLOCKED):
        socket.getaddrinfo("example.com", 443)


def test_mock_transport_still_works():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    assert client.get("https://openrouter.ai/x").status_code == 204


def test_real_keys_are_hidden():
    assert "OPENROUTER_API_KEY" not in os.environ and "GROQ_API_KEY" not in os.environ
