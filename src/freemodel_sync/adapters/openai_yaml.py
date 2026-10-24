"""Adapter for YAML configs that keep the LLM settings in a nested mapping.

Only three keys under ``key_path`` are managed: ``base_url``, ``model`` and
``fallback_models``.  Everything else in the document is kept, and when
nothing changed the file is left untouched byte-for-byte.

Comments: if the optional ``ruamel.yaml`` package is installed
(``pip install "freemodel-sync[yaml-comments]"``) the file is edited in
round-trip mode, so comments, key order and quoting survive a change.
Otherwise PyYAML is used, which drops comments when a value changes. The
``preserve_comments`` option selects ``auto`` (default: ruamel.yaml when
available), ``true`` (require it) or ``false`` (always PyYAML).

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

import io
from typing import Any, Dict, List, Optional

import yaml

from ..models import Selection
from .base import Adapter, register_adapter
from .openai_env import resolve_base_url


def _load_ruamel() -> Optional[Any]:
    """Return the ``ruamel.yaml`` module, or ``None`` when it is not installed."""

    try:
        import ruamel.yaml as ruamel_yaml
    except ImportError:
        return None
    return ruamel_yaml


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
        preserve_comments: ``"auto"`` (default), ``true`` or ``false``; see
            the module docstring.
    """

    name = "openai-yaml"

    def _ruamel(self) -> Optional[Any]:
        mode = self.options.get("preserve_comments", "auto")
        if isinstance(mode, str):
            mode = mode.strip().lower()
        if mode in (False, "false", "no", "off"):
            return None
        module = _load_ruamel()
        if module is None and mode in (True, "true", "yes", "on"):
            raise ValueError(
                "preserve_comments is true but ruamel.yaml is not installed; "
                'run: pip install "freemodel-sync[yaml-comments]"'
            )
        if mode not in ("auto", True, "true", "yes", "on"):
            raise ValueError(f"preserve_comments must be auto, true or false, got {mode!r}")
        return module

    def render(self, selection: Selection, current_text: str) -> str:
        key_path = str(self.options.get("key_path") or "llm")
        path = _parse_key_path(key_path)
        ruamel_yaml = self._ruamel()

        if ruamel_yaml is not None:
            rt = ruamel_yaml.YAML(typ="rt")
            rt.preserve_quotes = True
            rt.width = 1 << 16
            rt.indent(mapping=2, sequence=4, offset=2)
            try:
                data = rt.load(current_text) if current_text.strip() else None
            except ruamel_yaml.YAMLError as exc:
                raise ValueError(f"cannot parse YAML: {exc}") from exc
            if data is None:
                data = ruamel_yaml.comments.CommentedMap()
            new_map: Any = ruamel_yaml.comments.CommentedMap
        else:
            try:
                data = yaml.safe_load(current_text) if current_text.strip() else None
            except yaml.YAMLError as exc:
                raise ValueError(f"cannot parse YAML: {exc}") from exc
            if data is None:
                data = {}
            new_map = dict
        if not isinstance(data, dict):
            raise ValueError("expected the YAML document to be a mapping at the top level")

        node: Dict[str, Any] = data
        for part in path[:-1]:
            child = node.get(part)
            if child is None:
                child = new_map()
                node[part] = child
            elif not isinstance(child, dict):
                raise ValueError(f"cannot set {key_path!r}: {part!r} is not a mapping in the current document")
            node = child

        leaf_name = path[-1]
        leaf = node.get(leaf_name)
        if leaf is None:
            leaf = new_map()
            node[leaf_name] = leaf
        elif not isinstance(leaf, dict):
            raise ValueError(f"cannot set {key_path!r}: it is not a mapping in the current document")

        desired = {
            "base_url": resolve_base_url(selection.provider, self.options),
            "model": selection.primary.model.id,
            "fallback_models": [fallback.model.id for fallback in selection.fallbacks],
        }
        if current_text.strip() and all(leaf.get(k) == v for k, v in desired.items()):
            # Values already match: keep the file byte-for-byte (comments included).
            return current_text

        if ruamel_yaml is not None:
            for key, value in desired.items():
                if key == "fallback_models" and isinstance(leaf.get(key), list):
                    # Edit the existing sequence in place so its comments stay attached.
                    leaf[key][:] = value
                else:
                    leaf[key] = value
            out = io.StringIO()
            rt.dump(data, out)
            return out.getvalue()

        leaf.update(desired)
        return yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
