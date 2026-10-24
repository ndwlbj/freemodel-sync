"""Tests for scripts/daily_snapshot.py and its workflow (all HTTP is faked)."""

import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest
import yaml

from freemodel_sync.models import ModelInfo, QuotaInfo, TestResult
from freemodel_sync.providers import ProviderError, get_provider_class

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_snapshot.py"
spec = importlib.util.spec_from_file_location("daily_snapshot", SCRIPT)
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 1, 0, 5, tzinfo=timezone.utc)
KEY = "sk-or-v1-" + "a1b2c3d4" * 8
ENV = {"OPENROUTER_API_KEY": KEY}


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("SNAPSHOT_MAX_PROBES", raising=False)


class FakeProvider:
    def __init__(self, name="openrouter", models=(), outcomes=None, quota=None, discover_error=None):
        self.name = name
        self.api_key = KEY
        self._models = [m if isinstance(m, ModelInfo) else ModelInfo(name, m, m, 8192) for m in models]
        self.outcomes = outcomes or {}
        self._quota = quota
        self.discover_error = discover_error
        self.probed = []

    def discover(self):
        if self.discover_error:
            raise ProviderError(self.discover_error)
        return list(self._models)

    def quota(self):
        return self._quota

    def test(self, model, timeout=30.0):
        self.probed.append(model.id)
        kw = self.outcomes.get(model.id, {"ok": True, "ttft_ms": 120.4, "total_ms": 300.6})
        return TestResult(key=model.key, tested_at=1.0, **kw)


def run(tmp_path, providers, skipped=None, argv=(), env=ENV):
    out = tmp_path / "snapshots"
    code = ds.main(
        ["--out", str(out), "--date", TODAY.isoformat(), *argv],
        env=dict(env),
        providers=(providers, skipped or {}),
        now=NOW,
    )
    return code, out


def load(out, name="latest.json"):
    return json.loads((out / name).read_text())


# -- redaction --------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        f"invalid key {KEY}",
        "Authorization: Bearer abcdefghijklmnop",
        "headers={'Authorization': 'Bearer xyz123456789'}",
        "groq key gsk_ABCDEFGH12345678 rejected",
        "legacy sk-abcdefghijklmnop",
    ],
)
def test_redact_masks_key_patterns(text):
    redacted = ds.redact(text)
    for secret in (KEY, "abcdefghijklmnop", "xyz123456789", "gsk_ABCDEFGH12345678"):
        assert secret not in redacted
    assert "redacted" in redacted


def test_redact_masks_exact_secret_values_and_keeps_none():
    assert ds.redact("token=plainsecretvalue!", ["plainsecretvalue"]) == "token=<redacted>!"
    assert ds.redact(None) is None


def test_assert_no_secrets_refuses_output_with_a_key(tmp_path):
    with pytest.raises(ds.SecretLeakError):
        snap = ds.build_snapshot(
            [("openrouter", FakeProvider(models=["v/a:free"]))],
            {},
            today=TODAY,
            now=NOW,
            previous=None,
            max_probes=1,
            reserve=0,
            probe=False,
            timeout=1.0,
            expiring_days=14,
            secrets=[KEY],
        )
        snap["models"][0]["name"] = KEY  # e.g. an unredacted field slipped through
        ds.write_snapshot(tmp_path, snap, [KEY])
    assert not list(tmp_path.iterdir())


def test_key_in_provider_errors_never_reaches_the_snapshot(tmp_path):
    provider = FakeProvider(
        models=["v/a:free", "v/b:free"],
        outcomes={
            "v/a:free": {
                "ok": False,
                "status_code": 404,
                "error": f"no endpoints for key {KEY}",
                "failure_kind": "model",
            },
            "v/b:free": {
                "ok": False,
                "status_code": 401,
                "error": f"User not found. Bearer {KEY}",
                "failure_kind": "account",
            },
        },
        quota=QuotaInfo(daily_free_limit=50, daily_free_remaining=40),
    )
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    for name in ("latest.json", "latest.md", f"{TODAY}.json"):
        text = (out / name).read_text()
        assert KEY not in text
        assert "a1b2c3d4" not in text


def test_real_openrouter_provider_401_body_with_key_is_redacted(tmp_path):
    catalog = {
        "data": [
            {
                "id": "v/a:free",
                "name": "A",
                "context_length": 32000,
                "pricing": {"prompt": "0", "completion": "0"},
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "supported_parameters": ["tools"],
                "expiration_date": "2026-10-30",
            }
        ]
    }
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=catalog)
        if request.url.path.endswith("/key"):
            return httpx.Response(
                200,
                json={"data": {"free_model_daily_requests": {"limit": 50, "used": 5, "remaining": 45}, "usage": 1.5}},
            )
        return httpx.Response(401, json={"error": {"code": 401, "message": f"bad key {KEY}"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = get_provider_class("openrouter")(api_key=KEY, client=client)
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    snap = load(out)
    assert KEY not in json.dumps(snap) and KEY not in (out / "latest.md").read_text()
    assert snap["providers"]["openrouter"]["status"] == "account_error"
    quota = snap["providers"]["openrouter"]["quota"]
    assert quota.pop("note").startswith("read once before probing")
    assert quota == {
        "daily_free_limit": 50,
        "daily_free_used": 5,
        "daily_free_remaining": 45,
        "read": "before probing",
        "remaining_estimate": 44,
    }
    assert "usage" not in json.dumps(snap["providers"])
    assert snap["models"][0]["status"] == "401"
    assert snap["diff"]["expiring_soon"][0]["days_until_expiry"] == 8


# -- probing ----------------------------------------------------------------
def test_statuses_latency_and_context(tmp_path):
    provider = FakeProvider(
        models=["v/ok:free", "v/gate:free", "v/busy:free", "v/gone:free", "v/slow:free"],
        outcomes={
            "v/gate:free": {
                "ok": False,
                "status_code": 403,
                "error": "agentic harnesses only",
                "failure_kind": "model",
            },
            "v/busy:free": {"ok": False, "status_code": 429, "error": "upstream busy", "failure_kind": "transient"},
            "v/gone:free": {"ok": False, "status_code": 404, "error": "No endpoints", "failure_kind": "model"},
            "v/slow:free": {"ok": False, "error": "ReadTimeout: timed out", "failure_kind": "transient"},
        },
        quota=QuotaInfo(daily_free_limit=50, daily_free_remaining=45),
    )
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    by_id = {m["id"]: m for m in load(out)["models"]}
    assert {k: v["status"] for k, v in by_id.items()} == {
        "v/ok:free": "ok",
        "v/gate:free": "403",
        "v/busy:free": "429",
        "v/gone:free": "404",
        "v/slow:free": "timeout",
    }
    assert by_id["v/ok:free"]["ttft_ms"] == 120 and by_id["v/ok:free"]["total_ms"] == 301
    assert by_id["v/ok:free"]["context_length"] == 8192
    md = (out / "latest.md").read_text()
    assert "| openrouter | `v/ok:free` | ok | 120 | 301 | 8192 |" in md
    assert "informational only" in md


def test_probe_cap_applies_per_provider(tmp_path):
    provider = FakeProvider(
        models=[f"v/m{i}:free" for i in range(20)], quota=QuotaInfo(daily_free_limit=1000, daily_free_remaining=1000)
    )
    code, out = run(tmp_path, [("openrouter", provider)], argv=["--max-probes", "3"])
    assert code == 0
    assert len(provider.probed) == 3
    snap = load(out)
    assert snap["summary"] == {"models": 20, "ok": 3, "failed": 0, "not_probed": 17}
    assert snap["providers"]["openrouter"]["probes_sent"] == 3


def test_default_cap_is_15_and_env_overrides(tmp_path, monkeypatch):
    assert ds.build_parser().parse_args(["--out", "x"]).max_probes == 15
    monkeypatch.setenv("SNAPSHOT_MAX_PROBES", "4")
    assert ds.build_parser().parse_args(["--out", "x"]).max_probes == 4


def test_remaining_quota_and_reserve_limit_probes(tmp_path):
    provider = FakeProvider(
        models=[f"v/m{i}:free" for i in range(10)], quota=QuotaInfo(daily_free_limit=50, daily_free_remaining=12)
    )
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    assert len(provider.probed) == 2  # 12 remaining - 10 reserve
    assert "budget" in load(out)["providers"]["openrouter"]["stop_reason"]


def test_account_error_stops_probing(tmp_path):
    provider = FakeProvider(
        models=["v/a:free", "v/b:free", "v/c:free"],
        outcomes={
            "v/a:free": {"ok": False, "status_code": 429, "error": "free-models-per-day", "failure_kind": "account"}
        },
        quota=QuotaInfo(daily_free_remaining=40),
    )
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    assert provider.probed == ["v/a:free"]
    snap = load(out)
    statuses = {m["id"]: (m["status"], m["failure_kind"]) for m in snap["models"]}
    assert statuses["v/a:free"] == ("429", "account")
    assert statuses["v/b:free"] == ("not_probed", None)
    assert snap["providers"]["openrouter"]["status"] == "account_error"


def test_no_probe_sends_no_chat_request(tmp_path):
    provider = FakeProvider(models=["v/a:free"], quota=QuotaInfo(daily_free_limit=50))
    code, out = run(tmp_path, [("openrouter", provider)], argv=["--no-probe"])
    assert code == 0 and provider.probed == []
    snap = load(out)
    assert snap["mode"] == "no-probe" and snap["models"][0]["status"] == "not_probed"
    assert "sent no probe requests" in (out / "latest.md").read_text()


def test_missing_key_fails_with_hint(tmp_path, capsys):
    code, out = run(tmp_path, [("openrouter", FakeProvider())], env={})
    assert code == 2 and not out.exists()
    assert "OPENROUTER_API_KEY is not set" in capsys.readouterr().err


def test_discovery_failure_is_recorded_and_fails(tmp_path):
    provider = FakeProvider(discover_error="OpenRouter model discovery failed: ConnectError")
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 1
    assert load(out)["providers"]["openrouter"]["status"] == "error"


def test_non_chat_models_are_not_probed(tmp_path):
    provider = FakeProvider(models=["meta-llama/llama-guard-4-12b:free", "v/a:free"])
    run(tmp_path, [("openrouter", provider)])
    assert provider.probed == ["v/a:free"]


# -- groq -------------------------------------------------------------------
def test_groq_needs_key_and_free_plan():
    providers, skipped = ds.resolve_providers({"OPENROUTER_API_KEY": KEY})
    assert [n for n, _ in providers] == ["openrouter"] and "not set" in skipped["groq"]
    providers, skipped = ds.resolve_providers({"OPENROUTER_API_KEY": KEY, "GROQ_API_KEY": "gsk_x" * 4})
    assert [n for n, _ in providers] == ["openrouter"] and "GROQ_PLAN" in skipped["groq"]
    providers, skipped = ds.resolve_providers(
        {"OPENROUTER_API_KEY": KEY, "GROQ_API_KEY": "gsk_x" * 4, "GROQ_PLAN": "free"}
    )
    assert [n for n, _ in providers] == ["openrouter", "groq"] and skipped == {}


def test_skipped_and_second_provider_in_snapshot(tmp_path):
    groq = FakeProvider(name="groq", models=["llama-3.3-70b-versatile"])
    code, out = run(tmp_path, [("openrouter", FakeProvider(models=["v/a:free"])), ("groq", groq)])
    assert code == 0
    assert {m["provider"] for m in load(out)["models"]} == {"openrouter", "groq"}
    code, out = run(
        tmp_path, [("openrouter", FakeProvider(models=["v/a:free"]))], skipped={"groq": "GROQ_API_KEY not set"}
    )
    assert load(out)["providers"]["groq"] == {
        "status": "skipped",
        "reason": "GROQ_API_KEY not set",
        "discovered": 0,
        "probes_sent": 0,
    }


# -- files and diff ---------------------------------------------------------
def test_writes_dated_and_latest_files(tmp_path):
    code, out = run(tmp_path, [("openrouter", FakeProvider(models=["v/a:free"]))])
    assert code == 0
    assert sorted(p.name for p in out.iterdir()) == ["2026-10-22.json", "latest.json", "latest.md"]
    assert load(out) == load(out, "2026-10-22.json")
    snap = load(out)
    assert snap["date"] == "2026-10-22" and snap["generated_at"] == "2026-10-22T01:00:05Z"
    assert snap["schema_version"] == 1 and snap["diff"]["previous_date"] is None


def test_diff_against_most_recent_earlier_snapshot(tmp_path):
    out = tmp_path / "snapshots"
    out.mkdir()
    old = {"date": "2026-10-20", "models": [{"key": "openrouter|v/old:free", "status": "ok"}]}
    prev = {
        "date": "2026-10-21",
        "models": [
            {"key": "openrouter|v/gone:free", "status": "ok"},
            {"key": "openrouter|v/a:free", "status": "429"},
            {"key": "openrouter|v/b:free", "status": "not_probed"},
        ],
    }
    (out / "2026-10-20.json").write_text(json.dumps(old))
    (out / "2026-10-21.json").write_text(json.dumps(prev))
    (out / "2026-10-22.json").write_text(json.dumps({"date": "2026-10-22", "models": []}))  # same-day rerun
    soon = ModelInfo("openrouter", "v/new:free", "N", 4096, expiration_date=date(2026, 10, 25))
    provider = FakeProvider(models=["v/a:free", "v/b:free", soon])
    code, out = run(tmp_path, [("openrouter", provider)])
    diff = load(out)["diff"]
    assert diff["previous_date"] == "2026-10-21"
    assert diff["added"] == ["openrouter|v/new:free"]
    assert diff["removed"] == ["openrouter|v/gone:free"]
    assert diff["status_changed"] == [{"key": "openrouter|v/a:free", "from": "429", "to": "ok"}]
    assert diff["expiring_soon"] == [
        {"key": "openrouter|v/new:free", "expiration_date": "2026-10-25", "days_until_expiry": 3}
    ]
    md = (out / "latest.md").read_text()
    assert "Compared with 2026-10-21" in md and "`openrouter|v/new:free`: 2026-10-25 (3 days)" in md
    assert "Groq publishes no expiry dates" in md


def test_find_previous_ignores_junk(tmp_path):
    (tmp_path / "latest.json").write_text("{}")
    (tmp_path / "2026-13-40.json").write_text("{}")
    (tmp_path / "2026-10-01.json").write_text("not json")
    assert ds.find_previous(tmp_path, TODAY) is None
    assert ds.find_previous(tmp_path / "missing", TODAY) is None


def test_markdown_escapes_pipes():
    assert ds._cell("a|b\nc") == "a\\|b c" and ds._cell(None) == "-"


# -- workflow ---------------------------------------------------------------
def test_workflow_is_minimal_and_safe():
    path = ROOT / ".github" / "workflows" / "daily-snapshot.yml"
    text = path.read_text()
    data = yaml.safe_load(text)
    triggers = data[True]  # YAML 1.1 reads the bare key `on` as True
    assert triggers["schedule"] == [{"cron": "17 1 * * *"}]
    assert "workflow_dispatch" in triggers
    assert data["permissions"] == {"contents": "write"}
    assert data["concurrency"]["cancel-in-progress"] is False
    job = data["jobs"]["snapshot"]
    steps = job["steps"]
    checkout = steps[0]
    assert checkout["uses"].startswith("actions/checkout@") and checkout["with"]["persist-credentials"] is False
    for step in steps:
        if "uses" in step:
            assert len(step["uses"].split("@", 1)[1].split()[0]) == 40  # pinned to a commit SHA
    assert "41898282+github-actions[bot]@users.noreply.github.com" in text
    assert "refs/heads/data" in text and "--orphan data" in text
    assert "push --force" not in text and " -f " not in text
    assert "refs/heads/main" not in text
    gen = next(s for s in steps if s.get("name") == "Generate snapshot")
    assert "GITHUB_TOKEN" not in gen["env"]  # the step that runs the probes gets no write token
    assert gen["env"]["OPENROUTER_API_KEY"] == "${{ secrets.OPENROUTER_API_KEY }}"


def test_quota_is_marked_as_read_before_probing(tmp_path):
    """The counters are from before this run's probes and may lag (fix/openrouter-quota-lag)."""
    provider = FakeProvider(
        models=["v/a:free", "v/b:free", "v/c:free"],
        quota=QuotaInfo(daily_free_limit=50, daily_free_used=7, daily_free_remaining=43),
    )
    code, out = run(tmp_path, [("openrouter", provider)])
    assert code == 0
    info = load(out)["providers"]["openrouter"]
    assert info["probes_sent"] == 3
    assert info["quota"]["daily_free_used"] == 7 and info["quota"]["remaining_estimate"] == 40
    assert info["quota"]["read"] == "before probing"
    md = (out / "latest.md").read_text()
    assert "7 used / 43 left before this run, about 40 left after it (data may lag)" in md


def test_no_probe_quota_estimate_equals_reported(tmp_path):
    provider = FakeProvider(models=["v/a:free"], quota=QuotaInfo(daily_free_limit=50, daily_free_remaining=43))
    code, out = run(tmp_path, [("openrouter", provider)], argv=["--no-probe"])
    assert code == 0
    quota = load(out)["providers"]["openrouter"]["quota"]
    assert "remaining_estimate" not in quota and quota["daily_free_remaining"] == 43
    assert "- used / 43 left before this run (data may lag)" in (out / "latest.md").read_text()
