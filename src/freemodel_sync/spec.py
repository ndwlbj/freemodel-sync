"""Loader for the shared rule files in ``spec/`` (provider rules, ranking defaults).

``spec/`` is the single source of the rules that the Python package and the
dsh plugin (``plugins/dsh-freemodel``) must agree on: base URLs, key variable
names, how probe errors are classified, rate-limit header names and ranking
weights. Both sides run the cases in ``spec/conformance/``.

In a wheel the files live in ``freemodel_sync/spec/``; in a source checkout
(editable install, tests) they are read from the repository's ``spec/``.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: the spec_version this package implements
SUPPORTED_SPEC_VERSION = 1


class SpecError(RuntimeError):
    """The spec files are missing, unreadable or of an unsupported version."""


def spec_dir() -> Path:
    """Directory holding ``providers.json`` and ``ranking.json``."""

    here = Path(__file__).resolve().parent
    for candidate in (here / "spec", here.parents[1] / "spec"):
        if (candidate / "providers.json").is_file():
            return candidate
    raise SpecError("freemodel-sync spec files not found (expected freemodel_sync/spec or <repo>/spec)")


def _load(name: str) -> Dict[str, Any]:
    path = spec_dir() / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("spec_version") != SUPPORTED_SPEC_VERSION:
        raise SpecError(
            f"{path}: spec_version {data.get('spec_version') if isinstance(data, dict) else None!r} "
            f"is not supported (this freemodel-sync implements {SUPPORTED_SPEC_VERSION})"
        )
    return data


@cache
def providers_spec() -> Dict[str, Any]:
    return _load("providers.json")


@cache
def ranking_spec() -> Dict[str, Any]:
    return _load("ranking.json")


def provider_spec(name: str) -> Dict[str, Any]:
    """The spec entry of one provider (``KeyError`` if it has none)."""

    return providers_spec()["providers"][name]


# ---------------------------------------------------------------------------
# error classification rules
# ---------------------------------------------------------------------------
def _lookup(error_obj: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path (``metadata.provider_name``) from an error object; missing -> ``None``."""

    value: Any = error_obj
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _condition_matches(condition: Mapping[str, Any], error_obj: Mapping[str, Any]) -> bool:
    if "truthy" in condition:
        return bool(_lookup(error_obj, condition["truthy"]))
    if "notNull" in condition:
        return _lookup(error_obj, condition["notNull"]) is not None
    if "in" in condition:
        value = _lookup(error_obj, condition["in"])
        return isinstance(value, (str, int, float)) and value in condition.get("values", ())
    raise SpecError(f"unknown condition in error rule: {dict(condition)!r}")


def _rule_matches(rule: Mapping[str, Any], status_code: Optional[int], error_obj: Mapping[str, Any]) -> bool:
    if status_code is None:
        return False
    if "status" in rule and status_code not in rule["status"]:
        return False
    if "statusMin" in rule and status_code < rule["statusMin"]:
        return False
    when: Sequence[Mapping[str, Any]] = rule.get("when") or ()
    return not when or any(_condition_matches(c, error_obj) for c in when)


def classify_with(error_map: Mapping[str, Any], status_code: Optional[int], error_obj: Any) -> str:
    """Classify a non-200 probe response with an ``errorMap`` from the spec.

    Rules are tried in order; the first whose ``status`` / ``statusMin``
    matches and one of whose ``when`` conditions holds (or that has none)
    gives the failure kind. No match -> ``errorMap.default``.
    """

    obj: Mapping[str, Any] = error_obj if isinstance(error_obj, Mapping) else {}
    rules: List[Mapping[str, Any]] = error_map.get("preStream") or []
    for rule in rules:
        if _rule_matches(rule, status_code, obj):
            return str(rule["kind"])
    return str(error_map.get("default", "model"))


def default_error_map() -> Dict[str, Any]:
    return providers_spec()["defaultErrorMap"]


def provider_error_map(name: str) -> Dict[str, Any]:
    return provider_spec(name).get("errorMap") or default_error_map()
