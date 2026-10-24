"""Adapter for ``KEY=VALUE`` env files used by OpenAI-compatible clients.

The adapter manages exactly three variables: the API base URL, the primary
model and the comma-separated fallback list.  All other lines (comments, API
keys, unrelated settings) are preserved verbatim and in their original order.
The adapter never writes an API key.

Example output::

    # my tool config
    OPENAI_API_KEY=<your key, left untouched>
    OPENAI_BASE_URL=https://openrouter.ai/api/v1
    OPENAI_MODEL=deepseek/deepseek-chat:free
    OPENAI_FALLBACK_MODELS=qwen/qwen3-235b:free,meta-llama/llama-3.3-70b:free
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..models import Selection
from .base import Adapter, register_adapter

#: Comment emitted above variables that had to be appended.
MANAGED_HEADER = "# managed by freemodel-sync"

_ASSIGNMENT_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<export>export[ \t]+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(?P<value>.*)$"
)
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Last-resort base URLs for providers that may not be imported yet.
_KNOWN_BASE_URLS = {"openrouter": "https://openrouter.ai/api/v1"}

# Characters that make a bare ``KEY=value`` line ambiguous, so the value is
# wrapped in double quotes.
_NEEDS_QUOTES_RE = re.compile(r"[\s#'\"\\$`]")


def resolve_base_url(provider: str, options: Dict[str, Any]) -> str:
    """Return the OpenAI-compatible base URL to write for *provider*.

    Resolution order:

    1. the explicit ``base_url`` option;
    2. the ``provider_base_urls`` option mapping;
    3. the registered provider class's ``base_url`` (via ``get_provider_class``);
    4. a small built-in mapping (currently only OpenRouter).

    Raises:
        ValueError: when no base URL can be determined, so that callers do not
            silently write an empty ``..._BASE_URL=`` line.
    """

    explicit = options.get("base_url")
    if explicit:
        return str(explicit)

    mapping = options.get("provider_base_urls")
    if isinstance(mapping, dict):
        mapped = mapping.get(provider)
        if mapped:
            return str(mapped)

    try:
        # Importing the package (not just the module) registers built-in
        # providers such as OpenRouter.
        from ..providers import get_provider_class

        class_url = get_provider_class(provider).base_url
    except Exception:  # noqa: BLE001 - unknown/unimportable provider falls back
        class_url = ""
    if class_url:
        return str(class_url)

    if provider in _KNOWN_BASE_URLS:
        return _KNOWN_BASE_URLS[provider]

    raise ValueError(
        f"cannot determine the base URL for provider {provider!r}; "
        "pass the 'base_url' option or a 'provider_base_urls' mapping"
    )


def _split_ending(line: str) -> Tuple[str, str]:
    """Split *line* into its body and original line ending."""

    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith(("\n", "\r")):
        return line[:-1], line[-1]
    return line, ""


def _format_value(value: str) -> str:
    """Format an env value, quoting it only when necessary."""

    if value == "":
        return ""
    if _NEEDS_QUOTES_RE.search(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


@register_adapter
class OpenAIEnvAdapter(Adapter):
    """Write the primary model and fallbacks into an env file.

    Options:
        base_url_var: name of the base-URL variable (default ``OPENAI_BASE_URL``).
        model_var: name of the model variable (default ``OPENAI_MODEL``).
        fallbacks_var: name of the comma-separated fallback variable
            (default ``OPENAI_FALLBACK_MODELS``).
        base_url: explicit base URL to write.
        provider_base_urls: mapping of provider name to base URL.
    """

    name = "openai-env"

    def render(self, selection: Selection, current_text: str) -> str:
        base_url_var = str(self.options.get("base_url_var") or "OPENAI_BASE_URL")
        model_var = str(self.options.get("model_var") or "OPENAI_MODEL")
        fallbacks_var = str(self.options.get("fallbacks_var") or "OPENAI_FALLBACK_MODELS")

        for var in (base_url_var, model_var, fallbacks_var):
            if not _VAR_NAME_RE.match(var):
                raise ValueError(f"invalid environment variable name: {var!r}")

        base_url = resolve_base_url(selection.provider, self.options)
        model_id = selection.primary.model.id
        fallback_ids = ",".join(fallback.model.id for fallback in selection.fallbacks)

        desired: List[Tuple[str, str]] = [
            (base_url_var, _format_value(base_url)),
            (model_var, _format_value(model_id)),
            (fallbacks_var, _format_value(fallback_ids)),
        ]
        desired_names = {name for name, _value in desired}

        newline = "\r\n" if "\r\n" in current_text else "\n"
        lines = current_text.splitlines(keepends=True) if current_text else []
        found: set = set()
        rendered: List[str] = []

        for line in lines:
            body, ending = _split_ending(line)
            match = _ASSIGNMENT_RE.match(body)
            if match and match.group("name") in desired_names:
                name = match.group("name")
                value = next(v for n, v in desired if n == name)
                prefix = match.group("indent") + (match.group("export") or "")
                rendered.append(f"{prefix}{name}={value}{ending}")
                found.add(name)
            else:
                rendered.append(line)

        missing = [(name, value) for name, value in desired if name not in found]
        text = "".join(rendered)

        if missing:
            if text and not text.endswith(("\n", "\r")):
                text += newline
            has_header = any(_split_ending(line)[0].strip() == MANAGED_HEADER for line in rendered)
            if not has_header:
                text += MANAGED_HEADER + newline
            for name, value in missing:
                text += f"{name}={value}{newline}"

        return text
