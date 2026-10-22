"""Tests for scripts/catalog_watch.py (all HTTP is faked)."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "catalog_watch.py"
spec = importlib.util.spec_from_file_location("catalog_watch", SCRIPT)
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)

TODAY = date(2026, 1, 1)


def model(mid, prompt="0", expires=None, **extra):
    m = {
        "id": mid, "name": mid, "context_length": 8192,
        "pricing": {"prompt": prompt, "completion": prompt},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "supported_parameters": ["max_tokens"],
    }
    if expires:
        m["expiration_date"] = expires
    m.update(extra)
    return m


def healthy():
    return {"data": [
        model("a/one:free"),
        model("b/two:free", expires="2026-01-10"),
        model("c/three:free", expires="2026-03-01"),
        model("d/paid", prompt="0.000001"),
    ]}


def test_check_counts_free_and_lists_expiring():
    report = cw.check(healthy(), today=TODAY)
    assert report["anomalies"] == []
    assert report["total"] == 4 and report["free"] == 3
    assert report["expiring"] == [{"id": "b/two:free", "expires": "2026-01-10", "days": 9}]
    assert "`b/two:free`: 2026-01-10 (9 days)" in cw.render(report)


def test_check_flags_schema_changes_and_no_free_models():
    payload = {"data": [{"id": "x:free", "price": 0}, {"id": "y:free"}]}
    report = cw.check(payload, today=TODAY)
    assert any("pricing.prompt" in a for a in report["anomalies"])
    assert any("only 0 free models" in a for a in report["anomalies"])
    assert cw.check({"models": []}, today=TODAY)["anomalies"] == [
        "response has no `data` list (schema change?)"
    ]


class FakeGitHub:
    def __init__(self, issues=(), comments=()):
        self.issues = list(issues)
        self.comments = list(comments)
        self.calls = []

    def __call__(self, method, url, token=None, body=None):
        self.calls.append((method, url.split("/repos/o/r")[-1], body))
        if method == "GET" and url.endswith("/issues?state=open&per_page=100"):
            return self.issues
        if method == "GET" and "/comments" in url:
            return self.comments
        return {}


def bad_report():
    return cw.check({"data": []}, today=TODAY)


def test_issue_opened_once_and_deduplicated():
    gh = FakeGitHub()
    report = bad_report()
    assert cw.sync_issue(report, "body", repo="o/r", token="t", http=gh) == "opened"
    method, path, body = gh.calls[-1]
    assert (method, path) == ("POST", "/issues") and body["title"] == cw.ISSUE_TITLE
    assert cw.fingerprint(report) in body["body"]

    existing = {"number": 7, "title": cw.ISSUE_TITLE, "body": body["body"]}
    gh = FakeGitHub(issues=[existing])
    assert cw.sync_issue(report, "body", repo="o/r", token="t", http=gh) == "unchanged"
    assert [c[0] for c in gh.calls] == ["GET", "GET"]

    other = cw.check({"data": [{"id": "x"}]}, today=TODAY)
    gh = FakeGitHub(issues=[existing])
    assert cw.sync_issue(other, "body", repo="o/r", token="t", http=gh) == "commented"
    assert gh.calls[-1][:2] == ("POST", "/issues/7/comments")


def test_issue_closed_when_healthy_and_pull_requests_ignored():
    report = cw.check(healthy(), today=TODAY)
    pr = {"number": 3, "title": cw.ISSUE_TITLE, "pull_request": {}}
    assert cw.sync_issue(report, "ok", repo="o/r", token="t", http=FakeGitHub(issues=[pr])) == "none"
    gh = FakeGitHub(issues=[{"number": 7, "title": cw.ISSUE_TITLE, "body": ""}])
    assert cw.sync_issue(report, "ok", repo="o/r", token="t", http=gh) == "closed"
    assert gh.calls[-1] == ("PATCH", "/issues/7", {"state": "closed"})


def test_main_fetch_failure_and_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    def failing(method, url, token=None, body=None):
        raise OSError("boom")

    assert cw.main([], http=failing) == 1
    assert "could not fetch the model list" in summary.read_text()

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert cw.main(["--open-issue"], http=lambda *a, **k: healthy()) == 1
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_main_opens_issue_with_token(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    gh = FakeGitHub()

    def http(method, url, token=None, body=None):
        if url == cw.MODELS_URL:
            return {"data": []}
        return gh(method, url, token, body)

    assert cw.main(["--open-issue"], http=http) == 0
    assert "issue: opened" in capsys.readouterr().out


@pytest.mark.parametrize("workflow", ["ci.yml", "catalog-watch.yml"])
def test_workflows_pin_actions_by_sha(workflow):
    text = (SCRIPT.parents[1] / ".github" / "workflows" / workflow).read_text()
    uses = [line.split("uses:")[1].strip() for line in text.splitlines() if "uses:" in line]
    assert uses and all("@" in u and len(u.split("@")[1].split()[0]) == 40 for u in uses)
    if workflow == "catalog-watch.yml":
        assert "issues: write" in text and "contents: read" in text and "OPENROUTER" not in text
        assert "secrets." in text and text.count("secrets.") == 1
