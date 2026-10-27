"""Secret redaction shared by the CLI logger and the daily snapshot script.

Two layers, applied to every text that may reach a log, a cache file or the
snapshot output:

1. **Exact values.** Every API key the run actually uses is registered with
   :func:`register_secret` (the CLI does this when it reads the key from the
   environment) and replaced wherever it appears, whatever its format.
2. **Key shapes.** :data:`KEY_PATTERNS` masks strings that look like a key
   even when the value was never registered: OpenRouter ``sk-or-...``,
   DashScope / Bailian ``sk-ws-...`` / ``sk-sp-...`` (long, with ``.`` and
   ``_``), SenseNova and other ``sk-...`` keys, Groq ``gsk_...``, bearer
   tokens, ``Authorization`` headers and Telegram bot URLs.

The prefix is kept (``sk-ws-<redacted>``) so a log still says which kind of
key was involved; the secret part never survives.
"""

from __future__ import annotations

import re
import threading
from typing import Iterable, Optional, Pattern, Set, Tuple

#: values shorter than this are not registered: replacing them would mangle ordinary text
MIN_SECRET_LENGTH = 6

#: ``(pattern, replacement)``, most specific first
KEY_PATTERNS: Tuple[Tuple[Pattern[str], str], ...] = (
    (re.compile(r"(api\.telegram\.org/bot)[^/\s\"']+"), r"\1<redacted>"),
    (re.compile(r"(?i)(bearer\s+)[^\s\"',;]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?!bearer\b)[^\s\"',;]+"), r"\1<redacted>"),
    (re.compile(r"\b(sk-or-)[A-Za-z0-9._-]{4,}"), r"\1<redacted>"),
    (re.compile(r"\b(sk-(?:ws|sp)-)[A-Za-z0-9._-]{4,}"), r"\1<redacted>"),
    (re.compile(r"\b(sk-)[A-Za-z0-9._-]{8,}"), r"\1<redacted>"),
    (re.compile(r"\b(gsk_)[A-Za-z0-9_-]{8,}"), r"\1<redacted>"),
)

_lock = threading.Lock()
_registered: Set[str] = set()


def register_secret(value: Optional[str]) -> None:
    """Redact *value* from every later :func:`redact` call (no-op for short or empty values)."""

    if value and len(value) >= MIN_SECRET_LENGTH:
        with _lock:
            _registered.add(value)


def clear_secrets() -> None:
    """Forget all registered values (for tests)."""

    with _lock:
        _registered.clear()


def registered_secrets() -> Tuple[str, ...]:
    """The registered values, longest first (so a key containing another is masked whole)."""

    with _lock:
        return tuple(sorted(_registered, key=len, reverse=True))


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Mask registered values, the extra *secrets* and key-shaped strings in *text*."""

    values = sorted(
        {s for s in (*registered_secrets(), *secrets) if s and len(s) >= MIN_SECRET_LENGTH},
        key=len,
        reverse=True,
    )
    for value in values:
        text = text.replace(value, "<redacted>")
    for pattern, replacement in KEY_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
