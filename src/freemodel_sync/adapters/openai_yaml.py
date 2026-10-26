"""Adapter for YAML configs that keep the LLM settings in a nested mapping.

Only three keys under ``key_path`` are managed: ``base_url``, ``model`` and
``fallback_models``.  Everything else in the document is kept, and when
nothing changed the file is left untouched byte-for-byte.

Comments: if the optional ``ruamel.yaml`` package is installed
(``pip install "freemodel-sync[yaml-comments]"``) the file is edited in
round-trip mode, so comments, key order and quoting survive a change.
Otherwise PyYAML is used, which re-dumps the whole document when a value
changes: comments are dropped and unrelated values are re-typed or re-quoted
(``1.10`` becomes ``1.1``, ``yes`` becomes ``true``, ``0755`` becomes ``493``).
The ``preserve_comments`` option selects:

- ``auto`` (default): ruamel.yaml when available. Without it, PyYAML is used
  only when the re-dump loses nothing (no comments, every value written back
  unchanged, e.g. a file freemodel-sync itself wrote with PyYAML); otherwise
  the target fails and the file is left unchanged.
- ``true``: require ruamel.yaml.
- ``false``: always PyYAML, accepting the re-dump.

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
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..flags import parse_bool
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


#: A ``#`` at the start of a line or after whitespace: a comment, or (rarely) a
#: string containing " #". False positives only make the check stricter.
_COMMENT_RE = re.compile(r"(^|\s)#")


def _scalars(text: str) -> List[Tuple[str, Optional[str]]]:
    """The scalar tokens of *text* as ``(value, style)`` pairs, in order."""

    return [(token.value, token.style) for token in yaml.scan(text) if isinstance(token, yaml.ScalarToken)]


def _pyyaml_dump(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def _pyyaml_is_lossless(text: str, data: Any) -> bool:
    """True when re-dumping *data* with PyYAML keeps everything in *text*.

    That is: *text* has no comments and every scalar is written back with the
    same spelling and quoting (layout such as indentation may still change).
    """

    if _COMMENT_RE.search(text):
        return False
    try:
        return _scalars(text) == _scalars(_pyyaml_dump(data))
    except yaml.YAMLError:  # pragma: no cover - text was already parsed once
        return False


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

    def _mode(self) -> str:
        """``"auto"``, ``"true"`` or ``"false"`` from ``preserve_comments``."""

        mode = self.options.get("preserve_comments", "auto")
        if mode is None or (isinstance(mode, str) and mode.strip().lower() == "auto"):
            return "auto"
        try:
            return "true" if parse_bool(mode, name="preserve_comments", default=False) else "false"
        except ValueError:
            raise ValueError(f"preserve_comments must be auto, true or false, got {mode!r}") from None

    def _ruamel(self) -> Optional[Any]:
        mode = self._mode()
        if mode == "false":
            return None
        module = _load_ruamel()
        if module is None and mode == "true":
            raise ValueError(
                "preserve_comments is true but ruamel.yaml is not installed; "
                'run: pip install "freemodel-sync[yaml-comments]"'
            )
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

        if self._mode() == "auto" and current_text.strip():
            original = yaml.safe_load(current_text)
            if not _pyyaml_is_lossless(current_text, original):
                raise ValueError(
                    "refusing to rewrite this YAML without ruamel.yaml: PyYAML would drop its "
                    "comments and could change unrelated values (e.g. 1.10 -> 1.1, yes -> true, "
                    '0755 -> 493). Install ruamel.yaml (pip install "freemodel-sync[yaml-comments]") '
                    "or set preserve_comments: false in this target's options to accept a plain re-dump; "
                    "nothing was written"
                )
        leaf.update(desired)
        return _pyyaml_dump(data)
