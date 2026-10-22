"""Adapter for YAML configs that keep the LLM settings in a nested mapping.

Only three keys under ``key_path`` are managed: ``base_url``, ``model`` and
``fallback_models``.  Everything else in the document is kept. Note that PyYAML does not preserve
comments, so comments are lost when a value actually changes; when nothing
changed the file is left untouched byte-for-byte.

Example for the default ``key_path`` (``"llm"``)::

    llm:
      base_url: https://openrouter.ai/api/v1
      model: deepseek/deepseek-chat:free
      fallback_models:
        - qwen/qwen3-235b:free
      temperature: 0.2
    other_setting: true
"""

from __future__ import annotations

from typing import Any, Dict, List

import yaml

from ..models import Selection
from .base import Adapter, register_adapter
from .openai_env import resolve_base_url


def _parse_key_path(key_path: str) -> List[str]:
    """Split a dotted ``key_path`` into its components."""

    parts = [part.strip() for part in str(key_path).split(".") if part.strip()]
    if not parts:
        raise ValueError(f"invalid key_path {key_path!r}: expected a dotted mapping path")
    return parts


@register_adapter
class OpenAIYamlAdapter(Adapter):
    """Write the primary model and fallbacks into a YAML mapping.

    Options:
        key_path: dotted path of the mapping to update (default ``"llm"``).
        base_url: explicit base URL to write.
        provider_base_urls: mapping of provider name to base URL.
    """

    name = "openai-yaml"

    def render(self, selection: Selection, current_text: str) -> str:
        key_path = str(self.options.get("key_path") or "llm")
        path = _parse_key_path(key_path)

        try:
            data = yaml.safe_load(current_text) if current_text.strip() else None
        except yaml.YAMLError as exc:
            raise ValueError(f"cannot parse YAML: {exc}") from exc
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("expected the YAML document to be a mapping at the top level")

        node: Dict[str, Any] = data
        for part in path[:-1]:
            child = node.get(part)
            if child is None:
                child = {}
                node[part] = child
            elif not isinstance(child, dict):
                raise ValueError(
                    f"cannot set {key_path!r}: {part!r} is not a mapping in the current document"
                )
            node = child

        leaf_name = path[-1]
        leaf = node.get(leaf_name)
        if leaf is None:
            leaf = {}
            node[leaf_name] = leaf
        elif not isinstance(leaf, dict):
            raise ValueError(
                f"cannot set {key_path!r}: it is not a mapping in the current document"
            )

        desired = {
            "base_url": resolve_base_url(selection.provider, self.options),
            "model": selection.primary.model.id,
            "fallback_models": [fallback.model.id for fallback in selection.fallbacks],
        }
        if current_text.strip() and all(leaf.get(k) == v for k, v in desired.items()):
            # Values already match: keep the file byte-for-byte (comments included).
            return current_text
        leaf.update(desired)

        return yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
