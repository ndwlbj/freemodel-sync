"""Adapter for AstrBot's ``data/cmd_config.json``.

AstrBot has used two layouts for chat providers; both are supported:

* **v4.10.0 and later** (checked against AstrBot v4.29.1 source): connection
  details (``key``, ``api_base``, ``type``, ...) live in the top-level
  ``provider_sources`` list, and each entry of the top-level ``provider``
  list references one via ``provider_source_id`` and carries the model name
  in its own top-level ``model`` field.  AstrBot merges the two at load time
  (``ProviderManager.get_merged_provider_config``).
* **Legacy (before v4.10.0):** each ``provider`` entry is self-contained and
  the model name is ``model_config.model``.  Newer AstrBot versions migrate
  this layout on start-up, moving ``model_config.model`` to ``model``.

Only the model name of the entry whose ``id`` equals ``provider_id`` is
changed.  Keys, ``api_base`` and provider sources are never touched and no
provider is created (that would need your API key).  An entry that matches
neither layout raises :class:`ValueError` instead of being silently ignored.

AstrBot keeps its configuration in memory and rewrites the file when settings
are saved in the WebUI, so restart AstrBot after a change.  AstrBot provider
entries have no fallback list; only the primary model is written.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models import Selection
from .base import Adapter, register_adapter

LAYOUT_V4 = "v4"
LAYOUT_LEGACY = "legacy"


def detect_layout(data: Dict[str, Any], entry: Dict[str, Any]) -> str:
    """Return which AstrBot layout *entry* uses, or raise ``ValueError``."""

    entry_id = entry.get("id")
    source_id = entry.get("provider_source_id")
    if source_id:
        sources = data.get("provider_sources")
        if not isinstance(sources, list):
            raise ValueError(
                f"AstrBot provider {entry_id!r} references provider source {source_id!r}, "
                "but the config has no 'provider_sources' list; refusing to guess the layout"
            )
        known = [s.get("id") for s in sources if isinstance(s, dict)]
        if source_id not in known:
            raise ValueError(
                f"AstrBot provider {entry_id!r} references provider source {source_id!r}, "
                f"which is not in 'provider_sources' (known: {', '.join(map(str, known)) or 'none'})"
            )
        return LAYOUT_V4
    if isinstance(entry.get("model_config"), dict):
        return LAYOUT_LEGACY
    raise ValueError(
        f"unrecognized AstrBot provider structure for {entry_id!r}: expected either "
        "'provider_source_id' + 'model' (AstrBot >= 4.10) or 'model_config.model' (older "
        "versions). Please open an issue with your AstrBot version."
    )


@register_adapter
class AstrbotAdapter(Adapter):
    """Update the model of an existing AstrBot provider entry.

    Options:
        provider_id: required id of an existing entry in the top-level
            ``provider`` list (in AstrBot >= 4.10 this is the *model* entry,
            not the provider source).
    """

    name = "astrbot"

    def render(self, selection: Selection, current_text: str) -> str:
        provider_id = self.options.get("provider_id")
        if not provider_id:
            raise ValueError(
                "the 'astrbot' adapter requires the 'provider_id' option "
                "(the id of an existing provider in data/cmd_config.json)"
            )
        provider_id = str(provider_id)

        try:
            data = json.loads(current_text) if current_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"cannot parse AstrBot config JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("expected the AstrBot config to be a JSON object")

        providers = data.get("provider")
        if not isinstance(providers, list):
            raise ValueError("unrecognized AstrBot config: no top-level 'provider' list in data/cmd_config.json")

        target: Optional[Dict[str, Any]] = None
        available: List[str] = []
        for entry in providers:
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("id")
            if entry_id is not None:
                available.append(str(entry_id))
            if entry_id is not None and str(entry_id) == provider_id:
                target = entry
                break

        if target is None:
            known = ", ".join(sorted(available)) or "none"
            raise ValueError(
                f"AstrBot provider {provider_id!r} was not found in data/cmd_config.json "
                f"(existing provider ids: {known}). Add the provider in AstrBot first; "
                "this adapter deliberately does not create providers because that "
                "would need your API key."
            )

        model_id = selection.primary.model.id
        layout = detect_layout(data, target)
        if layout == LAYOUT_V4:
            if target.get("model") == model_id:
                return current_text
            target["model"] = model_id
        else:
            model_config = target["model_config"]
            if model_config.get("model") == model_id:
                return current_text
            model_config["model"] = model_id
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
