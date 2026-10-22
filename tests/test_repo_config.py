"""Repository automation files stay well-formed."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_dependabot_updates_pip_and_actions_weekly():
    data = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    assert data["version"] == 2
    updates = {u["package-ecosystem"]: u for u in data["updates"]}
    assert set(updates) == {"pip", "github-actions"}
    for update in updates.values():
        assert update["directory"] == "/"
        assert update["schedule"]["interval"] == "weekly"
