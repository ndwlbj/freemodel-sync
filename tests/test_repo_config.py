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


def test_python39_jobs_run_on_ubuntu_24_04():
    """setup-python has no 3.9 build for Ubuntu 26.04, so these jobs must not use ubuntu-latest."""
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    assert "3.9" in jobs["test"]["strategy"]["matrix"]["python-version"]
    assert jobs["test"]["runs-on"] == "ubuntu-24.04"
    assert jobs["minimum-deps"]["runs-on"] == "ubuntu-24.04"
    assert jobs["minimum-deps"]["name"] == "test (minimum dependency versions)"
    snapshot = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-snapshot.yml").read_text())
    assert snapshot["jobs"]["snapshot"]["runs-on"] == "ubuntu-24.04"
