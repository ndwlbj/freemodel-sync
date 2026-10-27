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


def test_ci_matrix_matches_supported_pythons():
    """requires-python, classifiers and the CI matrix agree (3.10 is the minimum, F9/F10)."""
    import re

    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'requires-python = ">=3.10"' in pyproject
    classifiers = re.findall(r"Programming Language :: Python :: (3\.\d+)", pyproject)
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    matrix = jobs["test"]["strategy"]["matrix"]["python-version"]
    assert matrix == classifiers == ["3.10", "3.11", "3.12", "3.13", "3.14"]
    assert 'target-version = "py310"' in pyproject and 'python_version = "3.10"' in pyproject
    assert jobs["minimum-deps"]["name"] == "test (minimum dependency versions)"
    min_steps = jobs["minimum-deps"]["steps"]
    assert any(step.get("with", {}).get("python-version") == "3.10" for step in min_steps)
    # pinned runner images: setup-python builds differ per image
    assert jobs["test"]["runs-on"] == "ubuntu-24.04"
    assert jobs["minimum-deps"]["runs-on"] == "ubuntu-24.04"
    snapshot = yaml.safe_load((ROOT / ".github" / "workflows" / "daily-snapshot.yml").read_text())
    assert all(job["runs-on"] == "ubuntu-24.04" for job in snapshot["jobs"].values())


def test_ci_runs_windows_and_macos():
    """F2/A5: the run lock and file handling are tested off Linux too."""
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    matrix = jobs["test-os"]["strategy"]["matrix"]
    assert set(matrix["os"]) == {"windows-latest", "macos-latest"}
    assert jobs["test-os"]["strategy"]["fail-fast"] is False


def test_tool_versions_are_pinned_once():
    """F4/F5: ruff and mypy only in pyproject's dev extra; build/twine pinned like release.yml."""
    import re

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "ruff==" not in ci and "mypy==" not in ci
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'"ruff==[0-9.]+"', pyproject) and re.search(r'"mypy==[0-9.]+"', pyproject)
    pins = re.findall(r'"(build|twine)==([0-9.]+)"', ci)
    assert sorted(pins) == sorted(re.findall(r'"(build|twine)==([0-9.]+)"', release)) and len(pins) == 2
    test_steps = yaml.safe_load(ci)["jobs"]["test"]["steps"]
    runs = " ".join(step.get("run", "") for step in test_steps)
    assert "mypy" in runs and "--cov=scripts" in runs and "--cov-branch" in runs


def test_wheel_ships_the_runtime_spec_files():
    """freemodel_sync.spec reads providers.json and ranking.json; both are force-included in the wheel."""

    pyproject = (ROOT / "pyproject.toml").read_text()
    for name in ("providers.json", "ranking.json"):
        assert f'"spec/{name}" = "freemodel_sync/spec/{name}"' in pyproject
    assert '"spec",' in pyproject  # sdist
    build = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]["build"]
    assert "spec.providers_spec()" in " ".join(step.get("run", "") for step in build["steps"])
