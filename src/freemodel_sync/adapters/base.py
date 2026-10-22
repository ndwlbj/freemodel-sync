"""Adapter interface: write a :class:`~freemodel_sync.models.Selection` into a tool's config.

Every adapter goes through :func:`write_if_changed`, which guarantees:

* idempotency: nothing is written when the rendered content is unchanged;
* ``dry_run``: show what would change, touch nothing;
* backup: the previous file is copied to ``<file>.bak-<timestamp>`` first
  (mode at most 0600), and only the newest ``keep_backups`` copies are kept;
* atomic replace via a temp file in the same directory;
* symlinks are followed: the real target file is backed up and replaced,
  and the link itself is left in place.
"""

from __future__ import annotations

import abc
import difflib
import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from ..models import Selection


@dataclass
class WriteResult:
    adapter: str
    path: str
    changed: bool
    written: bool
    backup: Optional[str] = None
    diff: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter,
            "path": self.path,
            "changed": self.changed,
            "written": self.written,
            "backup": self.backup,
        }


#: default number of backups kept per target file
DEFAULT_KEEP_BACKUPS = 5


def _backup_prefix(real_path: Path, backup_dir: Optional[Path]) -> Tuple[Path, str]:
    """Return ``(directory, filename prefix)`` used for backups of *real_path*."""

    if backup_dir is None:
        return real_path.parent, f"{real_path.name}.bak-"
    # Several targets may share a file name; tag backups with a short path hash.
    digest = hashlib.sha1(str(real_path).encode("utf-8")).hexdigest()[:8]
    return Path(backup_dir).expanduser(), f"{real_path.name}.{digest}.bak-"


def list_backups(path: Path, backup_dir: Optional[Path] = None) -> List[Path]:
    """Return existing backups of *path*, oldest first."""

    real = Path(os.path.realpath(Path(path).expanduser()))
    directory, prefix = _backup_prefix(real, backup_dir)
    if not directory.is_dir():
        return []
    found = [p for p in directory.iterdir() if p.name.startswith(prefix) and p.is_file()]
    # Timestamps in the name sort chronologically; mtime breaks rare ties.
    return sorted(found, key=lambda p: (p.name[len(prefix):], p.stat().st_mtime))


def _make_backup(real_path: Path, backup_dir: Optional[Path]) -> Path:
    directory, prefix = _backup_prefix(real_path, backup_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Microseconds keep names unique and chronologically sortable even when
    # several writes happen within one second.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = directory / f"{prefix}{stamp}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{prefix}{stamp}-{n}"
        n += 1
    # Backups can contain secrets (e.g. API keys in .env files): never make
    # them more readable than the original, and never group/other readable.
    mode = (real_path.stat().st_mode & 0o777) & 0o600
    data = real_path.read_bytes()
    fd = os.open(str(candidate), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(candidate, mode)  # umask may have narrowed it further; make it explicit
    return candidate


def _rotate_backups(real_path: Path, backup_dir: Optional[Path], keep: int) -> List[str]:
    """Delete the oldest backups so that at most *keep* remain."""

    backups = list_backups(real_path, backup_dir)
    removed: List[str] = []
    for old in backups[: max(0, len(backups) - keep)]:
        try:
            old.unlink()
            removed.append(str(old))
        except OSError:  # pragma: no cover - best effort
            pass
    return removed


def write_if_changed(
    path: Path,
    new_text: str,
    *,
    adapter: str,
    dry_run: bool = False,
    backup: bool = True,
    keep_backups: int = DEFAULT_KEEP_BACKUPS,
    backup_dir: Optional[Path] = None,
) -> WriteResult:
    """Write *new_text* to *path* only if it differs from the current content.

    Args:
        backup: make a backup of the current file before replacing it.
        keep_backups: how many backups of this file to keep (oldest are
            deleted first). ``0`` disables backups.
        backup_dir: directory for backups (default: next to the real file).
    """

    display_path = Path(path).expanduser()
    # Follow symlinks (dotfile repos, container mounts): replacing the link
    # with a regular file would silently detach it from the real config.
    path = Path(os.path.realpath(display_path))
    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if old_text == new_text:
        return WriteResult(adapter, str(display_path), changed=False, written=False)
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{display_path} (current)",
            tofile=f"{display_path} (new)",
        )
    )
    if dry_run:
        return WriteResult(adapter, str(display_path), changed=True, written=False, diff=diff)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[str] = None
    keep = max(0, int(keep_backups))
    if backup and keep > 0 and path.exists():
        backup_path = str(_make_backup(path, backup_dir))
    mode = path.stat().st_mode & 0o777 if path.exists() else None
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    if backup and keep > 0:
        _rotate_backups(path, backup_dir, keep)
    return WriteResult(adapter, str(display_path), changed=True, written=True, backup=backup_path, diff=diff)


class Adapter(abc.ABC):
    #: identifier used in the ``targets`` section of the config file
    name: str = ""

    def __init__(self, path: str, **options: Any) -> None:
        self.path = Path(path).expanduser()
        self.options = options

    @abc.abstractmethod
    def render(self, selection: Selection, current_text: str) -> str:
        """Return the full new file content given the current content ('' if missing)."""

    def apply(
        self,
        selection: Selection,
        *,
        dry_run: bool = False,
        backup: bool = True,
        keep_backups: int = DEFAULT_KEEP_BACKUPS,
        backup_dir: Optional[Path] = None,
    ) -> WriteResult:
        current = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        new_text = self.render(selection, current)
        return write_if_changed(
            self.path,
            new_text,
            adapter=self.name,
            dry_run=dry_run,
            backup=backup,
            keep_backups=keep_backups,
            backup_dir=backup_dir,
        )


_ADAPTERS: Dict[str, Type[Adapter]] = {}


def register_adapter(cls: Type[Adapter]) -> Type[Adapter]:
    if not cls.name:
        raise ValueError("adapter class must define a non-empty 'name'")
    _ADAPTERS[cls.name] = cls
    return cls


def get_adapter_class(name: str) -> Type[Adapter]:
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise ValueError(f"unknown adapter {name!r}; available: {', '.join(sorted(_ADAPTERS))}") from None


def available_adapters() -> list:
    return sorted(_ADAPTERS)
