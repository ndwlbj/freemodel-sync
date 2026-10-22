"""Adapter interface: write a :class:`~freemodel_sync.models.Selection` into a tool's config.

Every adapter goes through :func:`write_if_changed`, which guarantees:

* idempotency: nothing is written when the rendered content is unchanged;
* ``dry_run``: show what would change, touch nothing;
* backup: the previous file is copied to ``<file>.bak-<timestamp>`` first;
* atomic replace via a temp file in the same directory;
* symlinks are followed: the real target file is backed up and replaced,
  and the link itself is left in place.
"""

from __future__ import annotations

import abc
import difflib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Type

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


def write_if_changed(
    path: Path,
    new_text: str,
    *,
    adapter: str,
    dry_run: bool = False,
    backup: bool = True,
) -> WriteResult:
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
    if backup and path.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        candidate = path.with_name(f"{path.name}.bak-{stamp}")
        n = 1
        while candidate.exists():
            candidate = path.with_name(f"{path.name}.bak-{stamp}-{n}")
            n += 1
        shutil.copy2(path, candidate)
        backup_path = str(candidate)
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

    def apply(self, selection: Selection, *, dry_run: bool = False, backup: bool = True) -> WriteResult:
        current = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        new_text = self.render(selection, current)
        return write_if_changed(self.path, new_text, adapter=self.name, dry_run=dry_run, backup=backup)


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
