"""Built-in config adapters.

Importing this package registers every built-in adapter, so
``get_adapter_class("dsh")`` works after ``import freemodel_sync.adapters``.
"""

from __future__ import annotations

from . import astrbot, dsh, openai_env, openai_yaml  # noqa: F401  (register adapters)
from .base import (
    Adapter,
    WriteResult,
    available_adapters,
    get_adapter_class,
    write_if_changed,
)

__all__ = [
    "Adapter",
    "WriteResult",
    "available_adapters",
    "get_adapter_class",
    "write_if_changed",
]
