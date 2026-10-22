"""Review P2-2: durable writes that keep the original owner and mode."""

import os

import pytest

from freemodel_sync import fileio
from freemodel_sync.adapters.base import write_if_changed


def test_atomic_write_fsyncs_and_keeps_mode(tmp_path, monkeypatch):
    synced = []
    real_fsync = os.fsync
    monkeypatch.setattr(fileio.os, "fsync", lambda fd: synced.append(fd) or real_fsync(fd))
    target = tmp_path / "conf.env"
    target.write_text("A=1\n")
    os.chmod(target, 0o640)
    fileio.atomic_write_text(target, "A=2\n")
    assert target.read_text() == "A=2\n"
    assert target.stat().st_mode & 0o777 == 0o640
    assert len(synced) >= 2  # the file data and its directory
    assert [p.name for p in tmp_path.iterdir()] == ["conf.env"]  # no temp file left


def test_new_files_are_private(tmp_path):
    target = tmp_path / "sub" / "new.json"
    fileio.atomic_write_text(target, "{}\n")
    assert target.stat().st_mode & 0o777 == 0o600


def test_owner_is_copied_when_it_differs(tmp_path, monkeypatch):
    target = tmp_path / "conf.yml"
    target.write_text("a: 1\n")
    st = target.stat()
    calls = []
    monkeypatch.setattr(fileio, "_owner", lambda path: (st.st_uid + 1, st.st_gid + 1))
    monkeypatch.setattr(fileio.os, "chown", lambda path, uid, gid: calls.append((uid, gid)))
    write_if_changed(target, "a: 2\n", adapter="t", backup=False)
    assert calls == [(st.st_uid, st.st_gid)]


def test_chown_permission_error_is_ignored(tmp_path, monkeypatch):
    target = tmp_path / "conf.yml"
    target.write_text("a: 1\n")
    monkeypatch.setattr(fileio, "_owner", lambda path: (-1, -1))

    def deny(*args):
        raise PermissionError("not root")

    monkeypatch.setattr(fileio.os, "chown", deny)
    fileio.atomic_write_text(target, "a: 2\n")
    assert target.read_text() == "a: 2\n"


def test_failed_write_leaves_original_and_no_temp(tmp_path, monkeypatch):
    target = tmp_path / "conf.yml"
    target.write_text("a: 1\n")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(fileio.os, "replace", boom)
    with pytest.raises(OSError):
        fileio.atomic_write_text(target, "a: 2\n")
    assert target.read_text() == "a: 1\n"
    assert [p.name for p in tmp_path.iterdir()] == ["conf.yml"]
