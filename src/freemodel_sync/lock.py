"""Inter-process lock so overlapping runs (e.g. from cron) do not probe twice."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:  # POSIX only; on other platforms runs are not serialized
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows only
    fcntl = None  # type: ignore[assignment]


class LockedError(RuntimeError):
    """Another freemodel-sync run holds the lock."""


class RunLock:
    """Non-blocking ``flock`` on *path*, held for the lifetime of the context."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: Optional[int] = None

    def __enter__(self) -> RunLock:
        if fcntl is None:  # pragma: no cover
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise LockedError(
                f"another freemodel-sync run is in progress (lock file {self.path})"
            ) from exc
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        self._fd = fd
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._fd is not None and fcntl is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
