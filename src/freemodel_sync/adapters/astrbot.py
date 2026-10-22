"""Adapter for AstrBot's ``data/cmd_config.json``.

Format verified against the AstrBot docs: providers live in the top-level
``provider`` list, each entry has a ``type`` such as
``openai_chat_completion`` and a ``model_config.model`` field.  AstrBot >=4.x
WebUI versions may store providers differently, so this adapter is
experimental.

Only ``model_config.model`` of the entry whose ``id`` equals ``provider_id`` is
updated (``model_config`` is created when missing).  ``key`` and ``api_base``
are never touched.  The provider is never created, because that would require
the user's API key; a missing ``provider_id`` raises :class:`ValueError`.
AstrBot provider entries have no fallback list, so fallbacks are ignored.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models import Selection
from .base import Adapter, register_adapter


@register_adapter
class AstrbotAdapter(Adapter):
    """Update ``model_config.model`` of an existing AstrBot provider entry.

    Options:
        provider_id: required id of an existing entry in the top-level
            ``provider`` list.
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
        if providers is None:
            providers = []
            data["provider"] = providers
        if not isinstance(providers, list):
            raise ValueError("expected the AstrBot config's 'provider' to be a list")

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

        model_config = target.get("model_config")
        if model_config is None:
            model_config = {}
            target["model_config"] = model_config
        elif not isinstance(model_config, dict):
            raise ValueError(
                f"AstrBot provider {provider_id!r} has a non-mapping 'model_config'; "
                "refusing to overwrite it"
            )

        model_config["model"] = selection.primary.model.id
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
