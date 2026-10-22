from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from conftest import make_selection

from freemodel_sync.adapters import available_adapters, get_adapter_class, write_if_changed


def test_all_adapters_registered():
    assert {"openai-env", "openai-yaml", "dsh", "astrbot"} <= set(available_adapters())


def test_write_if_changed_backup_dry_run_idempotent(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("old\n")
    r = write_if_changed(p, "new\n", adapter="t", dry_run=True)
    assert r.changed and not r.written and "+new" in r.diff
    assert p.read_text() == "old\n"
    r = write_if_changed(p, "new\n", adapter="t")
    assert r.written and Path(r.backup).read_text() == "old\n"
    assert p.read_text() == "new\n"
    r = write_if_changed(p, "new\n", adapter="t")
    assert not r.changed and not r.written
    assert len(list(tmp_path.glob("f.txt.bak-*"))) == 1


def test_env_adapter_preserves_other_lines(tmp_path, selection):
    p = tmp_path / ".env"
    p.write_text("# my tool\nOPENAI_API_KEY=placeholder\nexport OPENAI_MODEL=old\nOTHER=1\n")
    a = get_adapter_class("openai-env")(str(p))
    res = a.apply(selection)
    text = p.read_text()
    assert res.written
    assert "OPENAI_API_KEY=placeholder\n" in text
    assert "export OPENAI_MODEL=vendor/a:free\n" in text
    assert "OPENAI_BASE_URL=https://openrouter.ai/api/v1" in text
    assert "OPENAI_FALLBACK_MODELS=vendor/b:free,vendor/c:free" in text
    assert text.count("# managed by freemodel-sync") == 1
    assert not a.apply(selection).changed  # idempotent


def test_env_adapter_custom_var_names(tmp_path, selection):
    p = tmp_path / "x.env"
    a = get_adapter_class("openai-env")(str(p), model_var="LLM_MODEL", base_url="https://example.invalid/v1")
    a.apply(selection)
    assert "LLM_MODEL=vendor/a:free" in p.read_text()
    assert "OPENAI_BASE_URL=https://example.invalid/v1" in p.read_text()


def test_yaml_adapter(tmp_path, selection):
    p = tmp_path / "c.yml"
    p.write_text("app:\n  llm:\n    temperature: 0.2\nother: true\n")
    a = get_adapter_class("openai-yaml")(str(p), key_path="app.llm")
    a.apply(selection)
    data = yaml.safe_load(p.read_text())
    assert data["other"] is True
    assert data["app"]["llm"] == {
        "temperature": 0.2,
        "base_url": "https://openrouter.ai/api/v1",
        "model": "vendor/a:free",
        "fallback_models": ["vendor/b:free", "vendor/c:free"],
    }
    # unchanged values -> file untouched even if a comment was added by the user
    p.write_text("# hand comment\n" + p.read_text())
    assert not a.apply(selection).changed


def test_yaml_adapter_rejects_non_mapping(tmp_path, selection):
    p = tmp_path / "c.yml"
    p.write_text("- a\n- b\n")
    with pytest.raises(ValueError):
        get_adapter_class("openai-yaml")(str(p)).apply(selection)


DSH_EXISTING = """# my patch
- id: other
  config:
    foo: 1   # keep me

# default model
- id: agent-default-model
  config: {provider: someprovider, model: 'old-model'}
"""


def test_dsh_adapter_replaces_only_managed_entry(tmp_path, selection):
    p = tmp_path / "bot-model.yml"
    p.write_text(DSH_EXISTING)
    a = get_adapter_class("dsh")(str(p), provider_map={"openrouter": "my-openrouter"})
    res = a.apply(selection)
    assert res.written and res.backup
    text = p.read_text()
    assert "    foo: 1   # keep me\n" in text and "# my patch\n" in text and "# default model\n" in text
    assert "- id: agent-default-model\n  config: {provider: my-openrouter, model: 'vendor/a:free'}\n" in text
    entries = yaml.safe_load(text)
    assert entries[1] == {
        "id": "agent-default-model",
        "config": {"provider": "my-openrouter", "model": "vendor/a:free"},
    }
    assert not a.apply(selection).changed


def test_dsh_adapter_new_file_exact_format(tmp_path, selection):
    p = tmp_path / "new" / "cordis.patch.yml"
    get_adapter_class("dsh")(str(p)).apply(selection)
    assert p.read_text() == "- id: agent-default-model\n  config: {provider: openrouter, model: 'vendor/a:free'}\n"


def test_dsh_adapter_quotes_and_fallback_entry(tmp_path):
    sel = make_selection(primary="we'ird:free", fallbacks=("b:free",))
    p = tmp_path / "p.yml"
    get_adapter_class("dsh")(str(p), fallback_entry_id="freemodel-fallbacks").apply(sel)
    entries = yaml.safe_load(p.read_text())
    assert entries[0]["config"]["model"] == "we'ird:free"
    assert entries[1] == {"id": "freemodel-fallbacks", "config": {"models": ["b:free"]}}


def test_dsh_adapter_rejects_mapping(tmp_path, selection):
    p = tmp_path / "p.yml"
    p.write_text("a: 1\n")
    with pytest.raises(ValueError):
        get_adapter_class("dsh")(str(p)).apply(selection)


ASTRBOT = {
    "provider": [
        {"id": "openrouter", "type": "openai_chat_completion", "provider_type": "chat_completion",
         "enable": True, "key": ["placeholder"], "api_base": "https://openrouter.ai/api/v1",
         "model_config": {"model": "old", "temperature": 0.4}},
        {"id": "other", "type": "openai_chat_completion", "model_config": {"model": "keep"}},
    ],
    "provider_settings": {"enable": True},
}


def test_astrbot_adapter_updates_model_only(tmp_path, selection):
    p = tmp_path / "cmd_config.json"
    p.write_text(json.dumps(ASTRBOT, indent=2))
    a = get_adapter_class("astrbot")(str(p), provider_id="openrouter")
    a.apply(selection)
    data = json.loads(p.read_text())
    assert data["provider"][0]["model_config"] == {"model": "vendor/a:free", "temperature": 0.4}
    assert data["provider"][0]["key"] == ["placeholder"]
    assert data["provider"][1]["model_config"]["model"] == "keep"
    assert not a.apply(selection).changed


def test_astrbot_adapter_requires_existing_provider(tmp_path, selection):
    p = tmp_path / "cmd_config.json"
    p.write_text(json.dumps(ASTRBOT))
    with pytest.raises(ValueError, match="not found"):
        get_adapter_class("astrbot")(str(p), provider_id="missing").apply(selection)
    with pytest.raises(ValueError, match="provider_id"):
        get_adapter_class("astrbot")(str(p)).apply(selection)


def test_write_follows_symlink(tmp_path, selection):
    """Review P1-2: a symlinked target must stay a symlink; the real file is updated."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real = real_dir / "real.env"
    real.write_text("OPENAI_MODEL=old\n")
    link = tmp_path / "link.env"
    link.symlink_to(real)

    res = get_adapter_class("openai-env")(str(link)).apply(selection)
    assert res.written and res.path == str(link)
    assert link.is_symlink() and link.resolve() == real.resolve()
    assert "OPENAI_MODEL=vendor/a:free" in real.read_text()
    assert Path(res.backup).parent == real_dir and Path(res.backup).read_text() == "OPENAI_MODEL=old\n"
    assert not get_adapter_class("openai-env")(str(link)).apply(selection).changed
