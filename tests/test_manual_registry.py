"""P9: tier-2 manual registration and local-only registry commands.

The fake key-shaped values are built at runtime, and the no-network test
monkeypatches httpx so a manual provider that ever tried to open a connection
would fail loudly.
"""

from __future__ import annotations

import json
import string
from datetime import date

import httpx
import pytest

from freemodel_sync.cli import _resolve_providers, _target_selection, main
from freemodel_sync.config import ConfigError, TargetConfig, load_config
from freemodel_sync.models import TestResult
from freemodel_sync.providers.manual import MANUAL_LABEL, ManualProvider
from freemodel_sync.ranking import rank, select

ALNUM = string.ascii_letters + string.digits


def _fake_key(prefix: str = "sk-", size: int = 40) -> str:
    return prefix + "".join(ALNUM[(index * 7 + 3) % len(ALNUM)] for index in range(size))


def _write(tmp_path, text: str):
    path = tmp_path / "config.yml"
    path.write_text(text, encoding="utf-8")
    return path


BASE = """
manual_providers:
  zcode:
    display_name: ZCode Start Plan (BigModel CN)
    auth: oauth_manual
    dsh_provider: dsh-zcode
    dsh_plugin: '@tnnevol/dsh-zcode'
    models:
      - id: glm-5.3
        tools: true
        quota: {unit: tokens, period: day, limit: 3000000, resets_at: "23:59+08:00"}
      - id: glm-5.3-flash
        tools: true
        quota: {unit: tokens, period: day, limit: 5000000}
  workbuddy:
    auth: oauth_manual
    models:
      - {id: deepseek-v4.1-flash, expires_at: "2020-01-01"}
      - {id: hy3, expires_at: "2020-01-01"}
"""


@pytest.mark.parametrize("field", ["token", "pat", "cookie", "password", "secret", "key"])
def test_config_rejects_credential_keys(tmp_path, field):
    path = _write(
        tmp_path,
        f"""
manual_providers:
  zcode:
    auth: oauth_manual
    models: [{{id: glm-5.3}}]
    {field}: not-a-real-value
""",
    )
    with pytest.raises(ConfigError, match="credential-bearing"):
        load_config(path)


def test_config_rejects_key_shaped_values(tmp_path):
    for label in (_fake_key(), "gsk_" + _fake_key("", 32), "Bearer " + _fake_key("", 32)):
        path = _write(
            tmp_path,
            f"""
manual_providers:
  zcode:
    auth: oauth_manual
    models:
      - id: glm-5.3
        name: '{label}'
""",
        )
        with pytest.raises(ConfigError, match="looks like an API key"):
            load_config(path)


def test_providers_section_also_rejects_a_key_shaped_option(tmp_path):
    path = _write(
        tmp_path,
        f"""
providers:
  openrouter:
    enabled: true
    api_key_env: OPENROUTER_API_KEY
    note: '{_fake_key()}'
""",
    )
    with pytest.raises(ConfigError, match="looks like an API key"):
        load_config(path)


def test_valid_manual_registry_loads_and_expires_by_date(tmp_path):
    cfg = load_config(_write(tmp_path, BASE))
    assert set(cfg.manual_providers) == {"zcode", "workbuddy"}
    provider = ManualProvider.from_config(cfg.manual_providers["workbuddy"], today=date(2026, 11, 2))
    assert provider.discover() == []
    assert cfg.manual_providers["workbuddy"].expired(today=date(2026, 11, 2)) is True
    assert cfg.manual_providers["workbuddy"].expired(today=date(2019, 12, 31)) is False


def test_discover_marks_manual_and_keeps_hand_entered_quota(tmp_path):
    cfg = load_config(_write(tmp_path, BASE))
    provider = ManualProvider.from_config(cfg.manual_providers["zcode"], today=date(2026, 10, 31))
    models = provider.discover()
    assert [model.id for model in models] == ["glm-5.3", "glm-5.3-flash"]
    assert all(model.tier == 2 and MANUAL_LABEL in model.name for model in models)
    quota = models[0].quota
    assert quota is not None and quota.source == "manual"
    assert quota.limit == 3_000_000 and quota.period == "day"
    assert provider.auth_kind == "oauth_manual" and provider.dsh_provider == "dsh-zcode"


def test_manual_entries_are_not_the_default_primary(tmp_path):
    cfg = load_config(_write(tmp_path, BASE))
    model = ManualProvider.from_config(cfg.manual_providers["zcode"], today=date(2026, 10, 31)).discover()[0]
    ranked = rank([model], {model.key: TestResult(key=model.key, ok=True, tested_at=1.0)})
    assert select(ranked) is None
    assert select(ranked, include_manual=True) is not None


def test_explicit_target_provider_can_select_a_manual_entry(tmp_path):
    cfg = load_config(_write(tmp_path, BASE))
    model = ManualProvider.from_config(cfg.manual_providers["zcode"], today=date(2026, 10, 31)).discover()[0]
    ranked = rank([model], {model.key: TestResult(key=model.key, ok=True, tested_at=1.0)})
    target = TargetConfig(adapter="openai-env", path=tmp_path / "env", options={"providers": ["zcode"]})
    selection = _target_selection(cfg, target, ranked)
    assert selection is not None and selection.primary.model.provider == "zcode"
    other = TargetConfig(adapter="openai-env", path=tmp_path / "env", options={"providers": ["openrouter"]})
    assert _target_selection(cfg, other, ranked) is None


def test_include_manual_off_by_default_in_resolve(tmp_path):
    cfg = load_config(_write(tmp_path, BASE))
    assert [name for name, _provider in _resolve_providers(cfg)] == ["openrouter"]
    assert [name for name, _provider in _resolve_providers(cfg, include_manual=True)] == [
        "openrouter",
        "zcode",
        "workbuddy",
    ]


def test_registry_list_and_check_json(tmp_path, capsys):
    path = _write(tmp_path, BASE)
    cfg = load_config(path)

    assert main(["registry", "list", "--json"], config=cfg) == 0
    listed = json.loads(capsys.readouterr().out)
    assert {entry["name"] for entry in listed} == {"zcode", "workbuddy"}
    assert "sk-" not in json.dumps(listed).lower()

    assert main(["registry", "check", "--json"], config=cfg) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["ok"] is True
    assert checked["network"].startswith("none")
    assert any("workbuddy" in warning and "expired" in warning for warning in checked["warnings"])


def test_registry_list_text_mentions_expired(tmp_path, capsys):
    cfg = load_config(_write(tmp_path, BASE))
    assert main(["registry", "list"], config=cfg) == 0
    output = capsys.readouterr().out
    assert "MANUAL PROVIDER" in output and "workbuddy" in output and "yes" in output


def test_manual_provider_makes_no_network_request(tmp_path, monkeypatch):
    cfg = load_config(_write(tmp_path, BASE))
    provider = ManualProvider.from_config(cfg.manual_providers["zcode"], today=date(2026, 10, 31))

    def boom(*_args, **_kwargs):
        raise AssertionError("ManualProvider must not create an HTTP client or open a connection")

    monkeypatch.setattr(httpx, "Client", boom)
    monkeypatch.setattr(httpx, "AsyncClient", boom)
    models = provider.discover()
    result = provider.test(models[0])
    assert result.ok is False
    assert "dsh" in (result.error or "")
    assert models[0].key.startswith("zcode|")
