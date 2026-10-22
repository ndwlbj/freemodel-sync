"""Review P2-8: openai-yaml keeps comments when ruamel.yaml is available."""

import pytest
import yaml

from freemodel_sync.adapters import get_adapter_class, openai_yaml
from freemodel_sync.models import ModelInfo, RankedModel, Selection, TestResult

DOC = """\
# Bot settings (hand-written)
app:
  name: "my bot"   # display name
  llm:
    # managed by freemodel-sync
    base_url: https://old.example/v1
    model: old/model   # previous choice
    fallback_models:
      - old/fb-1
    temperature: 0.2  # keep me
other: true
"""


def ranked(mid):
    return RankedModel(ModelInfo("openrouter", mid), 1.0, TestResult("openrouter|" + mid, True))


SEL = Selection(primary=ranked("vendor/a:free"), fallbacks=[ranked("vendor/b:free"), ranked("vendor/c:free")])
EXPECTED = {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "vendor/a:free",
    "fallback_models": ["vendor/b:free", "vendor/c:free"],
    "temperature": 0.2,
}


def apply(tmp_path, text, **options):
    p = tmp_path / "c.yml"
    p.write_text(text)
    result = get_adapter_class("openai-yaml")(str(p), key_path="app.llm", **options).apply(SEL, backup=False)
    return p.read_text(), result


def test_ruamel_preserves_comments_order_and_quotes(tmp_path):
    pytest.importorskip("ruamel.yaml")
    text, result = apply(tmp_path, DOC)
    assert result.changed
    data = yaml.safe_load(text)
    assert data["app"]["llm"] == EXPECTED and data["other"] is True and data["app"]["name"] == "my bot"
    for comment in ("# Bot settings (hand-written)", "# display name", "# managed by freemodel-sync",
                    "# keep me", "# previous choice"):
        assert comment in text, comment
    assert 'name: "my bot"' in text  # quoting kept
    assert text.index("base_url") < text.index("model:") < text.index("temperature")
    # second run: nothing changes, file untouched
    p = tmp_path / "c.yml"
    assert not get_adapter_class("openai-yaml")(str(p), key_path="app.llm").apply(SEL).changed


def test_ruamel_creates_missing_sections(tmp_path):
    pytest.importorskip("ruamel.yaml")
    text, _ = apply(tmp_path, "# only a comment\nother: 1\n")
    assert text.startswith("# only a comment\n")
    assert yaml.safe_load(text) == {"other": 1, "app": {"llm": {k: EXPECTED[k] for k in
                                                              ("base_url", "model", "fallback_models")}}}
    text, _ = apply(tmp_path, "")
    assert yaml.safe_load(text)["app"]["llm"]["model"] == "vendor/a:free"


def test_pyyaml_path_when_ruamel_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(openai_yaml, "_load_ruamel", lambda: None)
    text, result = apply(tmp_path, DOC)
    assert result.changed and yaml.safe_load(text)["app"]["llm"] == EXPECTED
    assert "#" not in text  # PyYAML drops comments (documented)


def test_preserve_comments_false_forces_pyyaml(tmp_path):
    text, _ = apply(tmp_path, DOC, preserve_comments=False)
    assert "#" not in text and yaml.safe_load(text)["app"]["llm"] == EXPECTED


def test_preserve_comments_true_requires_ruamel(tmp_path, monkeypatch):
    monkeypatch.setattr(openai_yaml, "_load_ruamel", lambda: None)
    with pytest.raises(ValueError, match="yaml-comments"):
        apply(tmp_path, DOC, preserve_comments=True)


def test_invalid_preserve_comments_value(tmp_path):
    with pytest.raises(ValueError, match="auto, true or false"):
        apply(tmp_path, DOC, preserve_comments="sometimes")


@pytest.mark.parametrize("use_ruamel", [True, False])
def test_both_paths_reject_bad_documents(tmp_path, monkeypatch, use_ruamel):
    if use_ruamel:
        pytest.importorskip("ruamel.yaml")
    else:
        monkeypatch.setattr(openai_yaml, "_load_ruamel", lambda: None)
    with pytest.raises(ValueError, match="mapping"):
        apply(tmp_path, "- a\n- b\n")
    with pytest.raises(ValueError, match="cannot parse YAML"):
        apply(tmp_path, "a: [1, 2\n")
    with pytest.raises(ValueError, match="not a mapping"):
        apply(tmp_path, "app: 3\n")
