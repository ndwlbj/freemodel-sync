"""One parser for on/off options written by hand in YAML.

YAML 1.1 turns ``yes``/``no``/``on``/``off`` into booleans, but quoted values
(``"false"``), numbers and other spellings reach the code as strings or ints.
Every on/off option goes through :func:`parse_bool` so they all accept the
same spellings, and anything else is an error instead of a silent guess.
"""

from __future__ import annotations

from typing import Any

TRUE_WORDS = frozenset({"true", "yes", "on", "1"})
FALSE_WORDS = frozenset({"false", "no", "off", "0"})


def parse_bool(value: Any, *, name: str, default: bool) -> bool:
    """Return *value* as a boolean.

    Accepts booleans, the integers ``0``/``1`` and the strings ``true``/``false``,
    ``yes``/``no``, ``on``/``off``, ``1``/``0`` (any case, surrounding spaces
    ignored). ``None`` (an empty YAML value) means *default*.

    Raises:
        ValueError: for any other value; the message names the option *name*.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
    raise ValueError(f"{name} must be true or false, got {value!r}")
