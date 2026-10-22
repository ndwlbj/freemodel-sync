"""Durable atomic file replacement shared by adapters, the cache and the state file."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union

PathLike = Union[str, "os.PathLike[str]"]


def _fsync_dir(directory: Path) -> None:
    if os.name != "posix":  # pragma: no cover - directories cannot be opened on Windows
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_text(path: PathLike, text: str) -> None:
    """Replace *path* with *text* atomically and durably.

    The data is fsynced before the rename and the directory afterwards. When
    *path* already exists its permission bits and, where allowed, its owner
    and group are copied to the new file, so running as root does not hand a
    user's config to root. New files are created with mode 0600.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        st = os.stat(path)
    except FileNotFoundError:
        st = None
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if st is not None:
            os.chmod(tmp, st.st_mode & 0o7777)
            if hasattr(os, "chown") and (st.st_uid, st.st_gid) != _owner(tmp):
                try:
                    os.chown(tmp, st.st_uid, st.st_gid)
                except OSError:
                    pass  # not permitted (e.g. not root): keep our own ownership
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    _fsync_dir(path.parent)


def _owner(path: PathLike) -> tuple:
    st = os.stat(path)
    return (st.st_uid, st.st_gid)
