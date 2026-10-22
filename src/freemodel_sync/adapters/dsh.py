"""Adapter for ``cordis.patch.yml``-style DSH model configuration.

The file is a YAML list of entries of the form ``{id, config}``.  This adapter
replaces the entry whose ``id`` equals ``entry_id`` (by default
``agent-default-model``) with::

    - id: agent-default-model
      config: {provider: openrouter, model: 'x/y:free'}

Other entries are preserved untouched and in their original order.  DSH
replaces an entry's whole ``config`` mapping, so only ``provider`` and
``model`` are written there.  Fallbacks are not part of this entry; set the
``fallback_entry_id`` option to additionally maintain an entry of the form
``{id: <fallback_entry_id>, config: {models: [...]}}``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..models import Selection
from .base import Adapter, register_adapter

#: Values matching this pattern can be emitted as plain YAML scalars.
_PLAIN_RE = re.compile(r"^[A-Za-z0-9_./:@+-]+$")


def _flow_scalar(value: str) -> str:
    """Render *value* as a YAML scalar safe inside a flow mapping."""

    text = str(value)
    if text and _PLAIN_RE.match(text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _single_quoted(value: str) -> str:
    """Render *value* as a single-quoted YAML scalar ('' escapes a quote)."""

    return "'" + str(value).replace("'", "''") + "'"


def _dump_other_entry(entry: Any) -> str:
    """Dump a non-managed entry as a YAML list item."""

    return yaml.safe_dump(
        [entry],
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _split_top_level_items(text: str) -> Optional[List[Tuple[str, str]]]:
    """Split a block-style YAML list into ``(leading_comments, item_text)`` pairs.

    A new item starts at every line beginning with ``"- "`` (or a bare ``"-"``)
    in column 0.  Blank and comment lines directly before an item belong to its
    leading text so they stay attached when the item is replaced.  Returns
    ``None`` if the text does not look like a block-style list.
    """

    lines = text.splitlines(keepends=True)
    items: List[Tuple[str, str]] = []
    pending = ""
    current: Optional[List[str]] = None
    lead = ""
    for line in lines:
        stripped = line.strip()
        is_item_start = line.startswith("- ") or line.rstrip("\r\n") == "-"
        if is_item_start:
            if current is not None:
                items.append((lead, "".join(current)))
            lead, pending = pending, ""
            current = [line]
        elif current is None:
            if stripped and not stripped.startswith("#") and stripped != "---":
                return None
            pending += line
        elif not stripped or (stripped.startswith("#") and not line.startswith((" ", "\t"))):
            pending += line
        else:
            if pending:
                current.append(pending)
                pending = ""
            current.append(line)
    if current is not None:
        items.append((lead, "".join(current)))
    return items


def _trailing_text(text: str) -> str:
    """Return trailing blank/comment lines after the last list item."""

    lines = text.splitlines(keepends=True)
    tail: List[str] = []
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped or (stripped.startswith("#") and not line.startswith((" ", "\t"))):
            tail.append(line)
        else:
            break
    return "".join(reversed(tail))


@register_adapter
class DshAdapter(Adapter):
    """Maintain the DSH default-model entry in a ``cordis.patch.yml`` file.

    Options:
        entry_id: id of the entry to manage (default ``agent-default-model``).
        provider_name: provider id to write; defaults to the selection's provider.
        provider_map: mapping such as ``{"openrouter": "my-dsh-provider"}`` used
            to translate a provider name into the user's DSH provider id.
        fallback_entry_id: optional id of an entry that stores the fallback
            model ids as ``config.models``.
    """

    name = "dsh"

    def _provider_name(self, selection: Selection) -> str:
        provider = selection.provider
        mapping = self.options.get("provider_map")
        if isinstance(mapping, dict) and provider in mapping:
            provider = str(mapping[provider])
        explicit = self.options.get("provider_name")
        if explicit:
            provider = str(explicit)
        return provider

    def _render_entry(self, entry_id: str, provider: str, model_id: str) -> str:
        return (
            f"- id: {_flow_scalar(entry_id)}\n"
            f"  config: {{provider: {_flow_scalar(provider)}, "
            f"model: {_single_quoted(model_id)}}}\n"
        )

    def _render_fallback_entry(self, entry_id: str, model_ids: List[str]) -> str:
        models = ", ".join(_single_quoted(model_id) for model_id in model_ids)
        return (
            f"- id: {_flow_scalar(entry_id)}\n"
            f"  config: {{models: [{models}]}}\n"
        )

    def render(self, selection: Selection, current_text: str) -> str:
        entry_id = str(self.options.get("entry_id") or "agent-default-model")
        fallback_entry_id = self.options.get("fallback_entry_id")
        fallback_entry_id = str(fallback_entry_id) if fallback_entry_id else None
        if fallback_entry_id and fallback_entry_id == entry_id:
            raise ValueError("fallback_entry_id must differ from entry_id")

        try:
            data = yaml.safe_load(current_text) if current_text.strip() else None
        except yaml.YAMLError as exc:
            raise ValueError(f"cannot parse YAML: {exc}") from exc
        if data is None:
            entries: List[Any] = []
        elif isinstance(data, list):
            entries = data
        else:
            raise ValueError("expected a YAML list of entries at the top level")

        provider = self._provider_name(selection)
        managed: Dict[str, str] = {
            entry_id: self._render_entry(entry_id, provider, selection.primary.model.id)
        }
        if fallback_entry_id:
            managed[fallback_entry_id] = self._render_fallback_entry(
                fallback_entry_id, [fallback.model.id for fallback in selection.fallbacks]
            )

        chunks = _split_top_level_items(current_text)
        if chunks is None or len(chunks) != len(entries):
            # Unusual layout (e.g. a flow-style list): fall back to re-dumping.
            chunks = [None] * len(entries)

        found: set = set()
        rendered: List[str] = []
        for entry, chunk in zip(entries, chunks):
            entry_name: Optional[str] = None
            if isinstance(entry, dict):
                raw_id = entry.get("id")
                if raw_id is not None:
                    entry_name = str(raw_id)
            if entry_name is not None and entry_name in managed and entry_name not in found:
                prefix = chunk[0] if chunk is not None else ""
                rendered.append(prefix + managed[entry_name])
                found.add(entry_name)
            elif chunk is not None:
                # Keep unmanaged entries byte-for-byte, comments included.
                rendered.append(chunk[0] + chunk[1])
            else:
                rendered.append(_dump_other_entry(entry))

        text = "".join(rendered)
        if text and not text.endswith("\n"):
            text += "\n"
        for name in (entry_id, fallback_entry_id):
            if name is not None and name not in found:
                text += managed[name]
        if chunks and chunks[-1] is not None:
            text += _trailing_text(current_text)
        return text
