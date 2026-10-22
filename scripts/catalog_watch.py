#!/usr/bin/env python3
"""Daily check of OpenRouter's public model list (no API key needed).

Fetches ``GET /api/v1/models``, checks that the fields freemodel-sync relies on
are still present, counts free models with freemodel-sync's own rules and lists
free models that expire soon. With ``--open-issue`` it opens (or updates) a
single GitHub issue when something looks wrong and closes it once the catalog
is healthy again. Only the standard library is used for HTTP; ``GITHUB_TOKEN``
and ``GITHUB_REPOSITORY`` come from the GitHub Actions environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from freemodel_sync.providers.openrouter import _is_free_model, _parse_expiration_date

MODELS_URL = "https://openrouter.ai/api/v1/models"
ISSUE_TITLE = "Catalog watch: OpenRouter model list needs attention"
MARKER = "<!-- catalog-watch:"
#: dotted paths freemodel-sync reads from each model object
KEY_FIELDS = (
    "id",
    "name",
    "context_length",
    "pricing.prompt",
    "pricing.completion",
    "architecture.input_modalities",
    "architecture.output_modalities",
    "supported_parameters",
)

Fetch = Callable[..., Any]


def _get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def check(
    payload: Any,
    *,
    today: Optional[date] = None,
    expiring_days: int = 14,
    min_free: int = 1,
    max_missing_ratio: float = 0.5,
) -> Dict[str, Any]:
    """Return a report dict; ``report["anomalies"]`` is empty when all is well."""

    today = today or datetime.now(timezone.utc).date()
    anomalies: List[str] = []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return {"total": 0, "free": 0, "missing": {}, "expiring": [],
                "anomalies": ["response has no `data` list (schema change?)"]}
    models = [m for m in data if isinstance(m, dict)]
    missing = {f: sum(1 for m in models if _get(m, f) is None) for f in KEY_FIELDS}
    for field, count in missing.items():
        if models and count / len(models) > max_missing_ratio:
            anomalies.append(f"field `{field}` missing from {count}/{len(models)} models")
    free = [m for m in models if _is_free_model(m)]
    if len(free) < min_free:
        anomalies.append(f"only {len(free)} free models detected (expected at least {min_free})")
    expiring = []
    for model in free:
        expires = _parse_expiration_date(model.get("expiration_date"))
        if expires is not None and (expires - today).days <= expiring_days:
            expiring.append({"id": model.get("id"), "expires": expires.isoformat(),
                             "days": (expires - today).days})
    expiring.sort(key=lambda item: (item["days"], str(item["id"])))
    return {"total": len(models), "free": len(free), "missing": missing,
            "expiring": expiring, "anomalies": anomalies}


def render(report: Dict[str, Any], expiring_days: int = 14) -> str:
    lines = [
        f"- models in catalog: {report['total']}",
        f"- free models (freemodel-sync rules): {report['free']}",
    ]
    if report["anomalies"]:
        lines += ["", "### Anomalies", ""] + [f"- {a}" for a in report["anomalies"]]
    lines += ["", f"### Free models expiring within {expiring_days} days", ""]
    lines += [f"- `{e['id']}`: {e['expires']} ({e['days']} days)" for e in report["expiring"]] or ["- none"]
    return "\n".join(lines) + "\n"


def fingerprint(report: Dict[str, Any]) -> str:
    return hashlib.sha256("\n".join(sorted(report["anomalies"])).encode()).hexdigest()[:16]


def _http(method: str, url: str, token: Optional[str] = None, body: Any = None, timeout: float = 30) -> Any:
    headers = {"Accept": "application/json", "User-Agent": "freemodel-sync-catalog-watch"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URLs
        text = response.read().decode("utf-8")
    return json.loads(text) if text else None


def sync_issue(report: Dict[str, Any], body: str, *, repo: str, token: str, http: Fetch = _http) -> str:
    """Open, update or close the single catalog-watch issue. Returns the action taken."""

    api = f"https://api.github.com/repos/{repo}"
    open_issues = http("GET", f"{api}/issues?state=open&per_page=100", token) or []
    existing = next(
        (i for i in open_issues if i.get("title") == ISSUE_TITLE and "pull_request" not in i), None
    )
    if not report["anomalies"]:
        if existing is None:
            return "none"
        http("POST", f"{api}/issues/{existing['number']}/comments", token,
             {"body": "The catalog check passes again; closing.\n\n" + body})
        http("PATCH", f"{api}/issues/{existing['number']}", token, {"state": "closed"})
        return "closed"

    marked = f"{body}\n{MARKER} {fingerprint(report)} -->\n"
    if existing is None:
        http("POST", f"{api}/issues", token, {"title": ISSUE_TITLE, "body": marked})
        return "opened"
    seen = [existing.get("body") or ""]
    comments = http("GET", f"{api}/issues/{existing['number']}/comments?per_page=100", token) or []
    seen += [c.get("body") or "" for c in comments]
    if any(f"{MARKER} {fingerprint(report)} -->" in text for text in seen):
        return "unchanged"
    http("POST", f"{api}/issues/{existing['number']}/comments", token, {"body": marked})
    return "commented"


def main(argv: Optional[List[str]] = None, *, http: Fetch = _http) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=MODELS_URL)
    parser.add_argument("--expiring-days", type=int, default=14)
    parser.add_argument("--min-free", type=int, default=1)
    parser.add_argument("--open-issue", action="store_true", help="open/update/close the GitHub issue")
    args = parser.parse_args(argv)

    try:
        payload = http("GET", args.url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        payload = None
        report = {"total": 0, "free": 0, "missing": {}, "expiring": [],
                  "anomalies": [f"could not fetch the model list: {type(exc).__name__}"]}
    else:
        report = check(payload, expiring_days=args.expiring_days, min_free=args.min_free)

    body = render(report, args.expiring_days)
    print(body)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## OpenRouter catalog watch\n\n" + body)

    if args.open_issue:
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not token or not repo:
            print("error: GITHUB_TOKEN and GITHUB_REPOSITORY are required for --open-issue", file=sys.stderr)
            return 1
        print(f"issue: {sync_issue(report, body, repo=repo, token=token, http=http)}")
    return 1 if report["anomalies"] and not args.open_issue else 0


if __name__ == "__main__":
    sys.exit(main())
