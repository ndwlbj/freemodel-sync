"""Adapter for ``cordis.patch.yml``-style DSH model configuration.

The file is a YAML list of entries of the form ``{id, config}``.  This adapter
replaces the entry whose ``id`` equals ``entry_id`` (by default
``agent-default-model``) with::

    - id: agent-default-model
      config: {provider: openrouter, model: 'x/y:free'}

Other entries are preserved untouched and in their original order.  DSH
replaces an entry's whole ``config`` mapping, so ``provider`` and ``model`` are
written there and any other keys already present in the managed entry's
``config`` (for example ``reasoningEffort``) are carried over.  An existing
``name`` field is kept; ``entry_name`` sets it explicitly (DSH skips a patch
entry whose ``name`` does not match the plugin's package name).

DSH has no fallback-list entry: verified against dsh 0.2.1-rc.2, an unknown
id such as ``freemodel-fallbacks`` is reported as ``patch: entry ... not
found`` and ignored.  The former ``fallback_entry_id`` option is therefore
deprecated and no longer written.

Before writing, the adapter checks the selected model against the provider's
model list when the same file declares that provider (an entry whose
``config.providers.<provider>.models`` is a list, as in dsh's ``llm-pi-ai``
entry). A model missing from that list raises ``ValueError``: dsh could not
use it, so the target is reported as failed and the file is left unchanged.
If the provider or its ``models`` list is not in this file (for example a
built-in dsh provider or one declared in another patch), nothing can be
checked and the entry is written as before. ``check_model: false`` disables
the check.

The file is edited line by line so other entries and comments stay
byte-for-byte. A layout that cannot be edited that way (for example a
flow-style list ``[{id: a, ...}]``) is refused with ``ValueError`` instead of
being re-dumped without its comments, and so is a file with two entries using
the managed ``entry_id`` (which one dsh would apply is not defined).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..flags import parse_bool
from ..models import Selection
from .base import Adapter, register_adapter

LOG = logging.getLogger(__name__)

#: A ``#`` at the start of a line or after whitespace (a YAML comment).
_COMMENT_RE = re.compile(r"(^|\s)#")

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


def _flow_value(value: Any) -> str:
    """Render any YAML-safe value on one line in flow style."""

    if isinstance(value, str):
        return _flow_scalar(value)
    text = yaml.safe_dump(value, default_flow_style=True, width=1 << 20, allow_unicode=True)
    text = text.strip()
    if text.endswith("\n..."):
        text = text[: -len("\n...")]
    elif text.endswith("..."):
        text = text[:-3].strip()
    return text


def _declared_models(entries: List[Any], provider: str) -> Optional[List[str]]:
    """Model ids declared for *provider* in this file, or ``None`` if it declares none.

    Looks at every entry whose ``config.providers`` is a mapping (dsh keeps
    them in the ``llm-pi-ai`` entry). Models may be mappings with an ``id``
    (dsh's format) or plain strings. Lists of several entries are combined.
    """

    found: Optional[List[str]] = None
    for entry in entries:
        config = entry.get("config") if isinstance(entry, dict) else None
        providers = config.get("providers") if isinstance(config, dict) else None
        spec = providers.get(provider) if isinstance(providers, dict) else None
        models = spec.get("models") if isinstance(spec, dict) else None
        if not isinstance(models, list):
            continue
        found = found or []
        for model in models:
            model_id = model.get("id") if isinstance(model, dict) else model
            if isinstance(model_id, (str, int, float)) and not isinstance(model_id, bool):
                found.append(str(model_id))
    return found


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
        entry_name: optional ``name`` to write into the entry, e.g.
            ``'@deepseek-ai/dsh-agent-default-model'``. An existing ``name`` is
            kept when this is not set.
        fallback_entry_id: deprecated and ignored (DSH has no such entry).
        check_model: when true (default), refuse to write a model that is not
            in the provider's ``models`` list declared in the same file.
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

    def _render_entry(
        self,
        entry_id: str,
        provider: str,
        model_id: str,
        *,
        name: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts = [f"provider: {_flow_scalar(provider)}", f"model: {_single_quoted(model_id)}"]
        for key, value in (extra or {}).items():
            parts.append(f"{_flow_value(key)}: {_flow_value(value)}")
        text = f"- id: {_flow_scalar(entry_id)}\n"
        if name:
            text += f"  name: {_single_quoted(name)}\n"
        return text + "  config: {" + ", ".join(parts) + "}\n"

    def render(self, selection: Selection, current_text: str) -> str:
        entry_id = str(self.options.get("entry_id") or "agent-default-model")
        if self.options.get("fallback_entry_id"):
            LOG.warning(
                "dsh: option fallback_entry_id is deprecated and ignored: DSH has no "
                "fallback-list entry (an unknown patch id is skipped with 'entry not found')"
            )

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
        model_id = selection.primary.model.id
        if parse_bool(self.options.get("check_model"), name="check_model", default=True):
            declared = _declared_models(entries, provider)
            if declared is None:
                LOG.info(
                    "dsh: provider %r has no models list in %s; model %r not checked",
                    provider,
                    self.path,
                    model_id,
                )
            elif model_id not in declared:
                raise ValueError(
                    f"model {model_id!r} is not in the models list of dsh provider {provider!r} "
                    f"in this file ({len(declared)} declared); dsh could not use it, so nothing "
                    "was written. Add the model to that provider, map to another provider with "
                    "provider_map/provider_name, or set check_model: false"
                )
        matching = [e for e in entries if isinstance(e, dict) and e.get("id") is not None and str(e["id"]) == entry_id]
        if len(matching) > 1:
            raise ValueError(
                f"{len(matching)} entries have id {entry_id!r}; which one dsh applies is not defined, "
                "so nothing was written. Remove the duplicates"
            )
        existing = matching[0] if matching else None
        name = self.options.get("entry_name") or (existing or {}).get("name")
        old_config = (existing or {}).get("config")
        extra = (
            {k: v for k, v in old_config.items() if k not in ("provider", "model")}
            if isinstance(old_config, dict)
            else {}
        )
        managed: Dict[str, str] = {
            entry_id: self._render_entry(
                entry_id,
                provider,
                model_id,
                name=str(name) if name else None,
                extra=extra,
            )
        }

        chunks: Optional[List[Tuple[str, str]]] = _split_top_level_items(current_text)
        if chunks is None or len(chunks) != len(entries):
            if entries or _COMMENT_RE.search(current_text):
                # Unusual layout (e.g. a flow-style list): re-dumping would drop
                # comments and reformat every entry, so refuse instead.
                raise ValueError(
                    "cannot edit this file in place: it is not a block-style YAML list with one "
                    "'- id: ...' item per entry (e.g. it uses a flow-style [ ... ] list). Rewriting it "
                    "would drop its comments and reformat other entries, so nothing was written. "
                    "Convert it to a block-style list"
                )
            chunks = []  # e.g. "[]": nothing to keep
            rendered: List[str] = []
        else:
            # Before the first entry, or the whole file when it only has
            # comments: kept as is.
            rendered = [] if chunks else [current_text]

        found: set = set()
        for entry, chunk in zip(entries, chunks, strict=True):
            entry_name: Optional[str] = None
            if isinstance(entry, dict):
                raw_id = entry.get("id")
                if raw_id is not None:
                    entry_name = str(raw_id)
            if entry_name is not None and entry_name in managed:
                rendered.append(chunk[0] + managed[entry_name])
                found.add(entry_name)
            else:
                # Keep unmanaged entries byte-for-byte, comments included.
                rendered.append(chunk[0] + chunk[1])

        text = "".join(rendered)
        if text and not text.endswith("\n"):
            text += "\n"
        if entry_id not in found:
            text += managed[entry_id]
        if chunks:
            text += _trailing_text(current_text)
        return text
