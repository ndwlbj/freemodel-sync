"""RunLock serializes runs on POSIX (flock) and Windows (msvcrt)."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from freemodel_sync import lock as lock_module
from freemodel_sync.lock import LockedError, RunLock


def test_platform_has_a_lock_backend():
    """A5: on Windows the lock used to be a silent no-op."""

    expected = "msvcrt" if sys.platform == "win32" else "fcntl"
    assert getattr(lock_module, expected) is not None


def test_second_lock_on_the_same_file_fails(tmp_path):
    path = tmp_path / "state.json.lock"
    with RunLock(path):
        with pytest.raises(LockedError, match="another freemodel-sync run is in progress"):
            with RunLock(path):
                pass  # pragma: no cover
    with RunLock(path):  # released on exit
        pass


def test_lock_is_released_after_an_exception(tmp_path):
    path = tmp_path / "x.lock"
    with pytest.raises(RuntimeError):
        with RunLock(path):
            raise RuntimeError("boom")
    with RunLock(path):
        pass


def test_lock_creates_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "state.lock"
    with RunLock(path):
        assert path.exists()


def test_lock_held_by_another_process(tmp_path):
    """The lock also excludes a different process, and dies with it."""

    path = tmp_path / "state.json.lock"
    code = textwrap.dedent(
        f"""
        import sys, time
        from freemodel_sync.lock import RunLock
        with RunLock({str(path)!r}):
            print("locked", flush=True)
            sys.stdin.readline()
        """
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(LockedError):
            with RunLock(path):
                pass  # pragma: no cover
    finally:
        child.kill()
        child.wait(timeout=30)
    with RunLock(path):  # the dead process's lock is gone, the file is reused
        pass
