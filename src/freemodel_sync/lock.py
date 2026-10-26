"""Inter-process lock so overlapping runs (e.g. from cron) do not probe twice."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class LockedError(RuntimeError):
    """Another freemodel-sync run holds the lock."""


class RunLock:
    """Non-blocking exclusive lock on *path*, held for the lifetime of the context.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` (a one-byte lock at
    offset 0) on Windows. Both locks belong to the open file, so the
    operating system releases them if the process dies; a stale lock file left
    behind does not block the next run.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: Optional[int] = None

    def __enter__(self) -> RunLock:
        if fcntl is None and msvcrt is None:  # pragma: no cover - neither POSIX nor Windows
            logger.warning("no file locking on this platform: overlapping runs are not serialized")
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            self._acquire(fd)
        except OSError as exc:
            os.close(fd)
            raise LockedError(f"another freemodel-sync run is in progress (lock file {self.path})") from exc
        if fcntl is not None:
            # Informational only. On Windows byte 0 is locked, and rewriting the
            # file is not needed for the lock to work, so it is left alone there.
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return self

    @staticmethod
    def _acquire(fd: int) -> None:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:  # pragma: no cover - Windows (covered by the Windows CI job)
            os.lseek(fd, 0, os.SEEK_SET)
            # LK_NBLCK fails at once (OSError) if another handle holds the byte.
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def __exit__(self, *exc: Any) -> None:
        if self._fd is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self._fd)
            self._fd = None
