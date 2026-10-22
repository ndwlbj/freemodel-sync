"""Regression tests: backups are capped, rotated and kept private (review P1-3)."""

from __future__ import annotations

import os
import stat

import pytest
import yaml

from freemodel_sync.adapters.base import list_backups, write_if_changed
from freemodel_sync.cli import main
from freemodel_sync.config import load_config


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_rotation_keeps_only_newest(tmp_path):
    p = tmp_path / "app.env"
    p.write_text("v0\n")
    for i in range(1, 8):
        write_if_changed(p, f"v{i}\n", adapter="t", keep_backups=3)
    backups = list_backups(p)
    assert len(backups) == 3
    assert [b.read_text() for b in backups] == ["v4\n", "v5\n", "v6\n"]


def test_keep_zero_disables_backups(tmp_path):
    p = tmp_path / "app.env"
    p.write_text("old\n")
    r = write_if_changed(p, "new\n", adapter="t", keep_backups=0)
    assert r.written and r.backup is None and list_backups(p) == []


@pytest.mark.parametrize("orig_mode, expected", [(0o600, 0o600), (0o644, 0o600), (0o400, 0o400), (0o640, 0o600)])
def test_backup_permissions_never_broader_than_0600(tmp_path, orig_mode, expected):
    p = tmp_path / "secrets.env"
    p.write_text("OPENAI_API_KEY=placeholder\n")
    os.chmod(p, orig_mode)
    r = write_if_changed(p, "OPENAI_API_KEY=placeholder\nX=1\n", adapter="t")
    assert _mode(r.backup) == expected
    assert _mode(p) == orig_mode  # the target keeps its own mode


def test_backup_dir_and_name_collisions(tmp_path):
    a = tmp_path / "a" / "config.yml"
    b = tmp_path / "b" / "config.yml"
    for f in (a, b):
        f.parent.mkdir()
        f.write_text("old\n")
    bdir = tmp_path / "backups"
    ra = write_if_changed(a, "new\n", adapter="t", backup_dir=bdir, keep_backups=1)
    rb = write_if_changed(b, "new\n", adapter="t", backup_dir=bdir, keep_backups=1)
    assert ra.backup != rb.backup and os.path.dirname(ra.backup) == str(bdir)
    assert len(list_backups(a, bdir)) == 1 and len(list_backups(b, bdir)) == 1
    assert not list(a.parent.glob("*.bak-*"))


def test_unrelated_files_are_never_rotated(tmp_path):
    p = tmp_path / "app.env"
    p.write_text("0\n")
    other = tmp_path / "app.env.bakery"
    other.write_text("keep")
    lookalike = tmp_path / "other.env.bak-20000101-000000"
    lookalike.write_text("keep")
    for i in range(4):
        write_if_changed(p, f"{i + 1}\n", adapter="t", keep_backups=1)
    assert other.exists() and lookalike.exists()


def test_config_and_per_target_override(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = tmp_path / "c.yml"
    cfg.write_text("backups: {keep: 2, dir: ~/bk}\n")
    c = load_config(cfg)
    assert c.backups.keep == 2 and "~" not in str(c.backups.dir)

    import time

    from freemodel_sync.models import ModelInfo, QuotaInfo, TestResult

    class Stub:
        api_key = "test-key"

        def __init__(self, model):
            self.model = model

        def discover(self):
            return [ModelInfo("openrouter", self.model, context_length=65536)]

        def test(self, model, timeout=30.0):
            return TestResult(model.key, True, ttft_ms=5.0, tested_at=time.time())

        def quota(self):
            return QuotaInfo(daily_free_limit=50, daily_free_remaining=50)

    target = tmp_path / "bot.yml"
    target.write_text("- id: agent-default-model\n  config: {provider: x, model: 'old'}\n")
    cfg.write_text(yaml.safe_dump({
        "backups": {"keep": 3},
        "testing": {"cache_path": str(tmp_path / "cache.json"), "cache_ttl_hours": 0.0001},
        "state_path": str(tmp_path / "state.json"),
        "targets": [{"adapter": "dsh", "path": str(target), "options": {"keep_backups": 1}}],
    }))
    for i in range(3):
        assert main(["-c", str(cfg), "sync", "--no-notify"],
                    provider_factory=lambda name, i=i, **kw: Stub(f"m{i}:free")) == 0
    assert len(list_backups(target)) == 1  # per-target override beats backups.keep=3
