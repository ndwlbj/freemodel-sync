#!/usr/bin/env python3
"""Daily free-model snapshot: discover, probe a capped number of models, write JSON + Markdown.

Used by ``.github/workflows/daily-snapshot.yml``; it can also run locally::

    OPENROUTER_API_KEY=... python scripts/daily_snapshot.py --out /tmp/snapshots --no-probe

What it does, reusing freemodel-sync's own providers and tester:

1. Discovers the free models of OpenRouter (always) and Groq (only when
   ``GROQ_API_KEY`` is set *and* ``GROQ_PLAN=free`` confirms a Free-plan
   organization, the same rule as ``providers.groq.plan: free``).
2. Reads OpenRouter's free-request quota (``/api/v1/key``,
   ``free_model_daily_requests``) and probes at most ``--max-probes`` models
   per provider, best static score first, keeping ``--reserve`` requests in
   reserve. An account/quota error (401/402, account-level 403, platform 429)
   stops probing of that provider, exactly like ``freemodel-sync test``.
   ``--no-probe`` sends no chat request at all (discovery and quota only).
3. Writes ``<out>/YYYY-MM-DD.json``, ``<out>/latest.json`` and
   ``<out>/latest.md``, with a diff against the most recent earlier snapshot
   in ``<out>`` (added, removed, expiring soon, status changes).

API keys never reach the output: error texts are redacted (``sk-or-...``,
``gsk_...``, ``Bearer ...`` and the exact key values) and the finished JSON is
checked for the key values before anything is written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from freemodel_sync import __version__
from freemodel_sync.models import ModelInfo, QuotaInfo, TestResult
from freemodel_sync.providers import ProviderError, get_provider_class
from freemodel_sync.ranking import RankWeights, filter_models, score_model
from freemodel_sync.tester import ResultCache, run_tests

SCHEMA_VERSION = 1
DEFAULT_MAX_PROBES = 15
DEFAULT_RESERVE = 10
DEFAULT_EXPIRING_DAYS = 14
DEFAULT_TIMEOUT_S = 30.0
#: assumed free requests/day when the provider reports nothing (as the CLI does)
FALLBACK_DAILY_FREE_LIMIT = 50
MAX_ERROR_CHARS = 200
_DATED_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")

_REDACT_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-or-[A-Za-z0-9_-]{4,}"), "sk-or-<redacted>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-<redacted>"),
    (re.compile(r"\bgsk_[A-Za-z0-9_-]{8,}"), "gsk_<redacted>"),
    (re.compile(r"(?i)(bearer\s+)[^\s\"',;]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]+"), r"\1<redacted>"),
)


class SecretLeakError(RuntimeError):
    """A key value was found in the rendered output; nothing is written."""


# ---------------------------------------------------------------------------
# redaction
# ---------------------------------------------------------------------------
def redact(text: Optional[str], secrets: Iterable[str] = ()) -> Optional[str]:
    """Mask API keys and auth headers in *text* (``None`` stays ``None``)."""

    if text is None:
        return None
    text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "<redacted>")
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def assert_no_secrets(rendered: str, secrets: Iterable[str]) -> None:
    for secret in secrets:
        if secret and len(secret) >= 6 and secret in rendered:
            raise SecretLeakError("an API key value appeared in the snapshot output; nothing was written")


# ---------------------------------------------------------------------------
# probing
# ---------------------------------------------------------------------------
def status_of(result: Optional[TestResult]) -> str:
    """Short status: ``ok``, the HTTP status (``403``/``404``/``429``...), ``timeout``,
    ``error`` (network or stream error without a status) or ``not_probed``."""

    if result is None:
        return "not_probed"
    if result.ok:
        return "ok"
    if "timeout" in (result.error or "").lower() and result.status_code in (None, 200):
        return "timeout"
    if result.status_code and result.status_code != 200:
        return str(result.status_code)
    return "error"


def _static_order(models: Sequence[ModelInfo], today: date) -> List[ModelInfo]:
    weights = RankWeights()

    def key(model: ModelInfo) -> Tuple[float, str]:
        score, _ = score_model(model, None, weights, today=today)
        return (-score, model.id)

    return sorted(models, key=key)


def _budget(quota: Optional[QuotaInfo]) -> Tuple[Optional[int], Optional[int]]:
    """``(daily_budget, remaining_budget)`` with the CLI's precedence."""

    if quota is not None and quota.daily_free_remaining is not None:
        return None, quota.daily_free_remaining
    if quota is not None and quota.daily_free_limit is not None:
        return quota.daily_free_limit, None
    return FALLBACK_DAILY_FREE_LIMIT, None


def snapshot_provider(
    name: str,
    provider: Any,
    *,
    today: date,
    max_probes: int,
    reserve: int,
    probe: bool,
    timeout: float,
    secrets: Sequence[str],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Discover (and optionally probe) one provider; return ``(provider_info, model_rows)``."""

    info: Dict[str, Any] = {"status": "ok", "discovered": 0, "probes_sent": 0}
    try:
        discovered = provider.discover()
    except ProviderError as exc:
        info.update(status="error", error=redact(str(exc), secrets)[:MAX_ERROR_CHARS])
        return info, []
    models = filter_models(
        list(discovered),
        exclude_expiring_within_days=None,
        exclude_non_chat=True,
        today=today,
    )
    models = _static_order(models, today)
    info["discovered"] = len(models)

    quota: Optional[QuotaInfo] = None
    quota_fn = getattr(provider, "quota", None)
    if callable(quota_fn):
        try:
            quota = quota_fn()
        except Exception as exc:  # noqa: BLE001 - quota is best effort
            info["quota_error"] = type(exc).__name__
    if quota is not None:
        # Only the free-request counters: no credit/usage figures in a public file.
        info["quota"] = {
            "daily_free_limit": quota.daily_free_limit,
            "daily_free_used": quota.daily_free_used,
            "daily_free_remaining": quota.daily_free_remaining,
        }

    results: Dict[str, TestResult] = {}
    account_error: Optional[TestResult] = None
    if probe:
        daily_budget, remaining = _budget(quota)
        with tempfile.TemporaryDirectory() as tmp:
            # A fresh cache: the snapshot reports today's probes, not old results.
            cache = ResultCache(Path(tmp) / "cache.json").load()
            run = run_tests(
                provider,
                models,
                cache=cache,
                max_tests=max_probes,
                daily_budget=daily_budget,
                remaining_budget=remaining,
                timeout=timeout,
                reserve=reserve,
            )
        results = dict(run)
        account_error = run.account_error
        info["probes_sent"] = run.probes
        if run.stop_reason:
            info["stop_reason"] = redact(run.stop_reason, secrets)[:MAX_ERROR_CHARS]
        if account_error is not None:
            info["status"] = "account_error"
    else:
        info["probing"] = "skipped (--no-probe)"

    rows: List[Dict[str, Any]] = []
    for model in models:
        result = results.get(model.key)
        if result is None and account_error is not None and account_error.key == model.key:
            result = account_error
        days = model.days_until_expiry(today)
        rows.append(
            {
                "key": model.key,
                "provider": model.provider,
                "id": model.id,
                "name": model.name,
                "context_length": model.context_length,
                "supports_tools": model.supports_tools,
                "expiration_date": model.expiration_date.isoformat() if model.expiration_date else None,
                "days_until_expiry": days,
                "status": status_of(result),
                "failure_kind": result.failure_kind if result is not None and not result.ok else None,
                "ttft_ms": round(result.ttft_ms) if result is not None and result.ttft_ms else None,
                "total_ms": round(result.total_ms) if result is not None and result.total_ms else None,
                "error": (
                    redact(result.error, secrets)[:MAX_ERROR_CHARS]
                    if result is not None and result.error
                    else None
                ),
            }
        )
    return info, rows


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
def find_previous(out_dir: Path, today: date) -> Optional[Dict[str, Any]]:
    """The most recent ``YYYY-MM-DD.json`` in *out_dir* dated before *today*."""

    best: Optional[Tuple[date, Path]] = None
    if not out_dir.is_dir():
        return None
    for path in out_dir.iterdir():
        match = _DATED_FILE.match(path.name)
        if not match:
            continue
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if day < today and (best is None or day > best[0]):
            best = (day, path)
    if best is None:
        return None
    try:
        data = json.loads(best[1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def compute_diff(
    rows: Sequence[Dict[str, Any]],
    previous: Optional[Dict[str, Any]],
    *,
    expiring_days: int,
) -> Dict[str, Any]:
    expiring = sorted(
        (
            {"key": r["key"], "expiration_date": r["expiration_date"], "days_until_expiry": r["days_until_expiry"]}
            for r in rows
            if r.get("days_until_expiry") is not None and r["days_until_expiry"] <= expiring_days
        ),
        key=lambda item: (item["days_until_expiry"], item["key"]),
    )
    diff: Dict[str, Any] = {
        "previous_date": None,
        "added": [],
        "removed": [],
        "status_changed": [],
        "expiring_within_days": expiring_days,
        "expiring_soon": expiring,
    }
    if previous is None:
        return diff
    prev_rows = {r.get("key"): r for r in previous.get("models") or [] if isinstance(r, dict) and r.get("key")}
    now_rows = {r["key"]: r for r in rows}
    diff["previous_date"] = previous.get("date")
    diff["added"] = sorted(set(now_rows) - set(prev_rows))
    diff["removed"] = sorted(set(prev_rows) - set(now_rows))
    for key in sorted(set(now_rows) & set(prev_rows)):
        before, after = prev_rows[key].get("status"), now_rows[key]["status"]
        if before != after and "not_probed" not in (before, after):
            diff["status_changed"].append({"key": key, "from": before, "to": after})
    return diff


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


_STATUS_ORDER = {"ok": 0}


def render_markdown(snapshot: Dict[str, Any]) -> str:
    lines: List[str] = [
        f"# Free-model snapshot {snapshot['date']}",
        "",
        "Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) "
        f"{snapshot['tool_version']}, generated {snapshot['generated_at']}. "
        "Results are informational only: one tiny request per model from GitHub Actions, "
        "so availability and latency can differ for you.",
        "",
    ]
    if snapshot["mode"] == "no-probe":
        lines += ["**This run sent no probe requests** (discovery and quota only).", ""]
    lines += ["## Providers", "", "| Provider | Status | Free models | Probes sent | Notes |", "|---|---|---|---|---|"]
    for name, info in snapshot["providers"].items():
        notes = [info.get("reason"), info.get("error"), info.get("stop_reason"), info.get("probing")]
        quota = info.get("quota")
        if quota and quota.get("daily_free_limit") is not None:
            notes.append(f"daily free limit {quota['daily_free_limit']}")
        lines.append(
            f"| {_cell(name)} | {_cell(info.get('status'))} | {_cell(info.get('discovered'))} | "
            f"{_cell(info.get('probes_sent'))} | {_cell('; '.join(n for n in notes if n))} |"
        )
    summary = snapshot["summary"]
    lines += [
        "",
        f"**{summary['models']}** free models, **{summary['ok']}** ok, {summary['failed']} failed, "
        f"{summary['not_probed']} not probed (probe cap {snapshot['max_probes']} per provider).",
        "",
        "## Models",
        "",
        "| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |",
        "|---|---|---|---|---|---|---|---|",
    ]

    def order(row: Dict[str, Any]) -> Tuple[int, float, str]:
        rank = _STATUS_ORDER.get(row["status"], 2 if row["status"] == "not_probed" else 1)
        return (rank, row.get("ttft_ms") or float("inf"), row["key"])

    for row in sorted(snapshot["models"], key=order):
        lines.append(
            f"| {_cell(row['provider'])} | `{_cell(row['id'])}` | {_cell(row['status'])} | "
            f"{_cell(row['ttft_ms'])} | {_cell(row['total_ms'])} | {_cell(row['context_length'])} | "
            f"{'yes' if row['supports_tools'] else 'no'} | {_cell(row['expiration_date'])} |"
        )

    diff = snapshot["diff"]
    lines += ["", "## Changes", ""]
    if diff["previous_date"] is None:
        lines.append("No earlier snapshot to compare with.")
    else:
        lines.append(f"Compared with {diff['previous_date']}:")
        lines.append("")
        lines.append(f"- Added: {', '.join(f'`{k}`' for k in diff['added']) or 'none'}")
        lines.append(f"- Removed: {', '.join(f'`{k}`' for k in diff['removed']) or 'none'}")
        changed = [f"`{c['key']}` {c['from']} -> {c['to']}" for c in diff["status_changed"]]
        lines.append(f"- Status changed: {', '.join(changed) or 'none'}")
    lines += ["", f"### Expiring within {diff['expiring_within_days']} days", ""]
    if diff["expiring_soon"]:
        for item in diff["expiring_soon"]:
            lines.append(f"- `{item['key']}`: {item['expiration_date']} ({item['days_until_expiry']} days)")
    else:
        lines.append("None announced.")
    lines += [
        "",
        "Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no "
        "expiry dates, so Groq models never appear here.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main flow
# ---------------------------------------------------------------------------
def build_snapshot(
    providers: Sequence[Tuple[str, Any]],
    skipped: Dict[str, str],
    *,
    today: date,
    now: datetime,
    previous: Optional[Dict[str, Any]],
    max_probes: int,
    reserve: int,
    probe: bool,
    timeout: float,
    expiring_days: int,
    secrets: Sequence[str],
) -> Dict[str, Any]:
    provider_info: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    for name, provider in providers:
        info, provider_rows = snapshot_provider(
            name, provider, today=today, max_probes=max_probes, reserve=reserve,
            probe=probe, timeout=timeout, secrets=secrets,
        )
        provider_info[name] = info
        rows.extend(provider_rows)
    for name, reason in skipped.items():
        provider_info[name] = {"status": "skipped", "reason": reason, "discovered": 0, "probes_sent": 0}

    ok = sum(1 for r in rows if r["status"] == "ok")
    not_probed = sum(1 for r in rows if r["status"] == "not_probed")
    return {
        "schema_version": SCHEMA_VERSION,
        "date": today.isoformat(),
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_version": __version__,
        "mode": "probe" if probe else "no-probe",
        "max_probes": max_probes,
        "reserve": reserve,
        "providers": provider_info,
        "summary": {"models": len(rows), "ok": ok, "failed": len(rows) - ok - not_probed, "not_probed": not_probed},
        "models": rows,
        "diff": compute_diff(rows, previous, expiring_days=expiring_days),
    }


def write_snapshot(out_dir: Path, snapshot: Dict[str, Any], secrets: Sequence[str]) -> List[Path]:
    rendered_json = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    rendered_md = render_markdown(snapshot)
    assert_no_secrets(rendered_json + rendered_md, secrets)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{snapshot['date']}.json", out_dir / "latest.json", out_dir / "latest.md"]
    for path, text in zip(paths, (rendered_json, rendered_json, rendered_md)):
        path.write_text(text, encoding="utf-8")
    return paths


def resolve_providers(env: Dict[str, str]) -> Tuple[List[Tuple[str, Any]], Dict[str, str]]:
    providers: List[Tuple[str, Any]] = [
        ("openrouter", get_provider_class("openrouter")(api_key=env.get("OPENROUTER_API_KEY") or None))
    ]
    skipped: Dict[str, str] = {}
    groq_key = env.get("GROQ_API_KEY") or ""
    groq_plan = (env.get("GROQ_PLAN") or "").strip().lower()
    if not groq_key:
        skipped["groq"] = "GROQ_API_KEY not set"
    elif groq_plan != "free":
        skipped["groq"] = "GROQ_PLAN is not 'free' (confirm a Free-plan organization; nothing probed)"
    else:
        providers.append(("groq", get_provider_class("groq")(api_key=groq_key, plan="free")))
    return providers, skipped


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="snapshots directory (read for the diff, written)")
    parser.add_argument(
        "--max-probes", type=_positive_int,
        default=int(os.environ.get("SNAPSHOT_MAX_PROBES") or DEFAULT_MAX_PROBES),
        help=f"probe at most N models per provider (default {DEFAULT_MAX_PROBES}, env SNAPSHOT_MAX_PROBES)",
    )
    parser.add_argument("--reserve", type=_positive_int, default=DEFAULT_RESERVE,
                        help=f"free requests to leave untouched (default {DEFAULT_RESERVE})")
    parser.add_argument("--no-probe", action="store_true", help="discovery and quota only; send no chat request")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per probe")
    parser.add_argument("--expiring-days", type=_positive_int, default=DEFAULT_EXPIRING_DAYS)
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="snapshot date (default: UTC today)")
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[Dict[str, str]] = None,
    providers: Optional[Tuple[List[Tuple[str, Any]], Dict[str, str]]] = None,
    now: Optional[datetime] = None,
) -> int:
    args = build_parser().parse_args(argv)
    env = dict(os.environ) if env is None else env
    if not env.get("OPENROUTER_API_KEY"):
        print(
            "error: OPENROUTER_API_KEY is not set. Add it as a repository secret "
            "(Settings > Secrets and variables > Actions) to run the daily snapshot.",
            file=sys.stderr,
        )
        return 2
    secrets = [v for k, v in env.items() if k.endswith(("_API_KEY", "_TOKEN")) and v]
    now = now or datetime.now(timezone.utc)
    today = args.date or now.astimezone(timezone.utc).date()
    resolved, skipped = providers if providers is not None else resolve_providers(env)

    started = time.monotonic()
    snapshot = build_snapshot(
        resolved, skipped, today=today, now=now,
        previous=find_previous(args.out, today),
        max_probes=args.max_probes, reserve=args.reserve, probe=not args.no_probe,
        timeout=args.timeout, expiring_days=args.expiring_days, secrets=secrets,
    )
    try:
        paths = write_snapshot(args.out, snapshot, secrets)
    except SecretLeakError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = snapshot["summary"]
    print(
        f"snapshot {snapshot['date']}: {summary['models']} models, {summary['ok']} ok, "
        f"{summary['failed']} failed, {summary['not_probed']} not probed "
        f"({sum(p.get('probes_sent', 0) for p in snapshot['providers'].values())} probes, "
        f"{time.monotonic() - started:.1f}s)"
    )
    for name, info in snapshot["providers"].items():
        if info["status"] not in ("ok", "skipped"):
            detail = info.get("stop_reason") or info.get("error") or ""
            print(f"::warning::{name}: {info['status']} {detail}".rstrip())
        elif info["status"] == "skipped":
            print(f"{name}: skipped ({info['reason']})")
    for path in paths:
        print(f"wrote {path}")
    if all(info["status"] == "error" for info in snapshot["providers"].values() if info["status"] != "skipped"):
        print("error: discovery failed for every provider", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
