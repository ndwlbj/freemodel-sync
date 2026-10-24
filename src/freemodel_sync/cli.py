"""Command line interface for freemodel-sync.

Commands::

    freemodel-sync [-c CONFIG] [-v] discover [--json]
    freemodel-sync [-c CONFIG] [-v] test [--max-tests N]
    freemodel-sync [-c CONFIG] [-v] rank [--json] [--output FILE]
    freemodel-sync [-c CONFIG] [-v] sync [--dry-run] [--no-notify]
    freemodel-sync [-c CONFIG] [-v] providers
    freemodel-sync [-c CONFIG] [-v] adapters
    freemodel-sync --version

API keys are only ever read from the environment variables named in the
config file; they are never printed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import __version__
from .adapters import available_adapters, get_adapter_class
from .config import Config, ConfigError, TargetConfig, load_config
from .fileio import atomic_write_text
from .lock import LockedError, RunLock
from .models import ModelInfo, QuotaInfo, Selection, TestResult
from .notify import notify_switch
from .providers import ProviderError, available_providers, get_provider_class
from .ranking import RankWeights, filter_models, rank, score_model, select
from .tester import ResultCache, TestRun, run_tests

logger = logging.getLogger(__name__)

ProviderFactory = Callable[..., Any]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _build_provider(
    name: str,
    api_key: Optional[str],
    options: Dict[str, Any],
    provider_factory: Optional[ProviderFactory] = None,
) -> Any:
    """Instantiate a provider.

    By default this is ``get_provider_class(name)(api_key=..., **options)``.
    Tests can inject ``provider_factory(name, api_key=..., **options)``.
    """

    if provider_factory is None:
        return get_provider_class(name)(api_key=api_key, **options)
    return provider_factory(name, api_key=api_key, **options)


#: ``[(name, provider), ...]`` for every enabled provider, in config order
Providers = List[Tuple[str, Any]]


def _resolve_providers(
    config: Config,
    provider_factory: Optional[ProviderFactory] = None,
) -> Providers:
    """Instantiate every enabled provider, in config order."""

    names = config.enabled_providers()
    if not names:
        raise ConfigError("no providers are enabled in the config")
    providers: Providers = []
    for name in names:
        settings = config.providers[name]
        api_key = os.environ.get(settings.api_key_env) if settings.api_key_env else None
        provider = _build_provider(name, api_key or None, dict(settings.options), provider_factory)
        providers.append((name, provider))
    return providers


def _resolve_provider(
    config: Config,
    provider_factory: Optional[ProviderFactory] = None,
) -> Tuple[str, Any]:
    """Return ``(name, provider)`` for the first enabled provider (kept for API users)."""

    return _resolve_providers(config, provider_factory)[0]


def _cache_path(config: Config, provider_name: str, first: bool) -> Path:
    """Probe cache file for one provider.

    The first enabled provider keeps ``testing.cache_path`` (so existing caches
    stay valid); others get ``<stem>.<provider><suffix>`` next to it. Separate
    files keep each provider's daily counter and rate-limit block apart.
    """

    path = Path(config.testing.cache_path)
    if first:
        return path
    return path.with_name(f"{path.stem}.{provider_name}{path.suffix or '.json'}")


def _dash(value: Any) -> str:
    return "-" if value is None else str(value)


def _safe_quota(provider: Any) -> Optional[QuotaInfo]:
    """Call ``provider.quota()`` defensively; never fail a command over it."""

    quota_fn = getattr(provider, "quota", None)
    if not callable(quota_fn):
        return None
    try:
        return quota_fn()
    except Exception as exc:  # noqa: BLE001 - quota is best effort
        logger.warning("could not read provider quota: %s", type(exc).__name__)
        return None


def _discover_by_provider(config: Config, providers: Providers) -> Dict[str, List[ModelInfo]]:
    """Discover and filter free models of every provider.

    With several providers, one that fails (network error, missing key for a
    provider whose model list needs one) is reported and skipped; the command
    fails only if every provider fails.
    """

    found: Dict[str, List[ModelInfo]] = {}
    errors: List[str] = []
    for name, provider in providers:
        try:
            found[name] = _discover_one(config, provider)
        except ProviderError as exc:
            if len(providers) == 1:
                raise
            errors.append(f"{name}: {exc}")
            print(f"warning: skipping provider {name}: {exc}", file=sys.stderr)
    if errors and not found:
        raise ProviderError("every provider failed: " + "; ".join(errors))
    return found


def _discover(config: Config, providers: Any) -> List[ModelInfo]:
    """Discover and filter free models of all providers (or of one provider object)."""

    if not isinstance(providers, list):
        return _discover_one(config, providers)
    by_provider = _discover_by_provider(config, providers)
    return [model for models in by_provider.values() for model in models]


def _discover_one(config: Config, provider: Any) -> List[ModelInfo]:
    models = provider.discover()
    if not isinstance(models, list):
        models = list(models)
    filters = config.filters
    return filter_models(
        models,
        require_tools=filters.require_tools,
        min_context=filters.min_context,
        exclude_expiring_within_days=filters.exclude_expiring_within_days,
        include=filters.include,
        exclude=filters.exclude,
        exclude_non_chat=filters.exclude_non_chat,
        today=date.today(),
    )


def _static_order(
    models: Sequence[ModelInfo],
    weights: RankWeights,
    today: Optional[date] = None,
) -> List[ModelInfo]:
    """Order models by their static score (``test=None``), best first.

    Probing is expensive and quota-limited, so the most promising models
    (tools, large context, not expiring soon) are tested before the rest.
    """

    today = today or date.today()

    def key(model: ModelInfo) -> Tuple[float, str]:
        score, _reasons = score_model(model, None, weights, today=today)
        return (-score, model.id)

    return sorted(models, key=key)


#: conservative free requests/day assumed when the provider reports nothing
FALLBACK_DAILY_FREE_LIMIT = 50

#: exit code when probing was stopped by an account/quota problem
EXIT_ACCOUNT_ERROR = 3
#: another run holds the lock (nothing was probed or written)
EXIT_LOCKED = 4


class MissingKeyError(RuntimeError):
    """Probing was requested but the provider has no API key."""


def _probe_all(
    config: Config,
    providers: Providers,
    by_provider: Dict[str, List[ModelInfo]],
    *,
    max_tests: Optional[int] = None,
    no_probe: bool = False,
) -> Tuple[TestRun, Dict[str, Optional[QuotaInfo]]]:
    """Probe every provider's models with that provider's own cache and budget.

    ``max_tests`` applies per provider. A provider without an API key is
    skipped with a warning; only when no provider has a key is that an error.
    An account/quota problem stops probing for that provider only.
    """

    merged = TestRun()
    quotas: Dict[str, Optional[QuotaInfo]] = {}
    reasons: List[str] = []
    missing: List[str] = []
    first_name = config.enabled_providers()[0] if config.enabled_providers() else None
    for name, provider in providers:
        models = by_provider.get(name)
        if models is None:
            continue
        try:
            run, quota = _probe(
                config, name, provider, models,
                max_tests=max_tests, no_probe=no_probe,
                cache_path=_cache_path(config, name, first=name == first_name),
                quiet=len(providers) > 1,
            )
        except MissingKeyError as exc:
            if len(providers) == 1:
                raise
            missing.append(name)
            print(f"warning: not probing {name}: {exc}", file=sys.stderr)
            continue
        quotas[name] = quota
        merged.update(run)
        merged.probes += run.probes
        merged.rate_limited = merged.rate_limited or run.rate_limited
        if run.account_error is not None and merged.account_error is None:
            merged.account_error = run.account_error
        if run.stop_reason:
            reasons.append(f"{name}: {run.stop_reason}" if len(providers) > 1 else run.stop_reason)
    if missing and len(missing) == len([n for n, _ in providers if n in by_provider]):
        raise MissingKeyError(
            "no enabled provider has an API key set ("
            + ", ".join(f"{n}: {config.providers[n].api_key_env or '?'}" for n in missing)
            + "). No requests were sent and nothing was cached."
        )
    if reasons:
        merged.stop_reason = "; ".join(reasons)
        if len(providers) > 1:
            print(f"warning: probing stopped: {merged.stop_reason}", file=sys.stderr)
    return merged, quotas


def _probe(
    config: Config,
    provider_name: str,
    provider: Any,
    models: Sequence[ModelInfo],
    *,
    max_tests: Optional[int] = None,
    no_probe: bool = False,
    cache_path: Optional[Path] = None,
    quiet: bool = False,
) -> Tuple[TestRun, Optional[QuotaInfo]]:
    """Run probes with the configured cache, TTL and free-request budget.

    With ``no_probe`` only fresh cached results are used: no API key is
    needed, no request is sent (not even ``/key``) and the cache is not written.

    Budget precedence: ``testing.daily_free_limit`` (user override, checked
    against the local UTC-day counter) > ``remaining`` reported by the
    provider > the provider's reported daily ``limit`` > a conservative 50.
    Without an API key nothing is probed, counted or cached.
    """

    cache_file = cache_path if cache_path is not None else config.testing.cache_path
    if no_probe:
        cache = ResultCache(cache_file).load()
        run = TestRun()
        for model in models:
            cached = cache.get(model.key, config.testing.cache_ttl_s, config.testing.transient_ttl_s)
            if cached is not None:
                run[model.key] = cached
        return run, None

    if not getattr(provider, "api_key", None):
        env = config.providers[provider_name].api_key_env or "the provider's API key"
        raise MissingKeyError(
            f"{env} is not set: testing models needs your own key "
            "(discover works without one). No requests were sent and nothing was cached."
        )

    quota = _safe_quota(provider)
    cache = ResultCache(cache_file).load()
    daily_budget: Optional[int] = None
    remaining: Optional[int] = None
    override = config.providers[provider_name].options.get("daily_free_limit") \
        if provider_name in config.providers else None
    if override is None:
        override = config.testing.daily_free_limit
    if override is not None:
        daily_budget = int(override)
    elif quota is not None and quota.daily_free_remaining is not None:
        remaining = quota.daily_free_remaining
        local = cache.requests_today()
        if quota.daily_free_limit is not None and local > (quota.daily_free_used or 0):
            # The provider's counter trails probes this tool already sent today:
            # trust the larger (local) count so the reserve is not overrun.
            remaining = min(remaining, max(0, quota.daily_free_limit - local))
    elif quota is not None and quota.daily_free_limit is not None:
        daily_budget = quota.daily_free_limit
    else:
        daily_budget = FALLBACK_DAILY_FREE_LIMIT

    limit = config.testing.max_tests if max_tests is None else max_tests
    run = run_tests(
        provider,
        models,
        cache=cache,
        max_tests=limit,
        cache_ttl_s=config.testing.cache_ttl_s,
        transient_ttl_s=config.testing.transient_ttl_s,
        daily_budget=daily_budget,
        remaining_budget=remaining,
        timeout=config.testing.timeout_s,
        reserve=config.testing.reserve_requests,
    )
    if quota is not None:
        quota.probes_since_read = run.probes
    if run.stop_reason and not quiet:
        print(f"warning: probing stopped: {run.stop_reason}", file=sys.stderr)
    return run, quota


def _selection_dict(selection: Optional[Selection]) -> Optional[Dict[str, Any]]:
    if selection is None:
        return None
    return {
        "provider": selection.provider,
        "primary": selection.primary.model.id,
        "primary_key": selection.primary.model.key,
        "fallbacks": [fallback.model.id for fallback in selection.fallbacks],
        "untested_fallbacks": selection.untested_fallbacks,
        "model_ids": selection.model_ids,
        "primary_model": selection.primary.to_dict(),
        "fallback_models": [fallback.to_dict() for fallback in selection.fallbacks],
    }


def _ranking_payload(
    provider_names: Sequence[str],
    ranked: Sequence[Any],
    selection: Optional[Selection],
    quotas: Dict[str, Optional[QuotaInfo]],
) -> Dict[str, Any]:
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "providers": list(provider_names),
        "quota": {name: (q.to_dict() if q is not None else None) for name, q in quotas.items()},
        "ranking": [item.to_dict() for item in ranked],
        "selection": _selection_dict(selection),
    }


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically write *payload* as pretty JSON, creating parent directories."""

    atomic_write_text(Path(path).expanduser(), json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """Print a simple left-aligned text table."""

    text_rows = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in text_rows:
        for index, cell in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(cell))
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)).rstrip())
    print("  ".join("-" * width for width in widths))
    for row in text_rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())


def _fallback_list(selection: Selection) -> str:
    """Comma-separated fallbacks; untested ones are flagged."""

    parts = [
        f"{f.model.id} (untested)" if f.test is None else f.model.id for f in selection.fallbacks
    ]
    return ", ".join(parts) or "none"


def _status(test: Optional[TestResult]) -> str:
    if test is None:
        return "untested"
    if test.ok:
        return "ok"
    return "transient" if test.failure_kind == "transient" else "failed"


def _read_state(path: Path) -> Dict[str, Any]:
    """Read the state file; missing/corrupt files yield an empty mapping."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, selection: Selection, targets: Optional[Dict[str, str]] = None) -> None:
    payload: Dict[str, Any] = {
        "primary": selection.primary.model.key,
        "provider": selection.provider,
        "model": selection.primary.model.id,
        "fallbacks": [fallback.model.id for fallback in selection.fallbacks],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if targets:
        payload["targets"] = dict(targets)
    _write_json(Path(path), payload)


def _write_partial_state(path: Path, previous: Dict[str, Any], targets: Dict[str, str]) -> None:
    """Record per-target successes without moving the global ``primary``."""

    payload = dict(previous)
    payload["targets"] = {**(previous.get("targets") or {}), **targets}
    payload["partial_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(Path(path), payload)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _cmd_discover(args: argparse.Namespace, config: Config, providers: Providers) -> int:
    by_provider = _discover_by_provider(config, providers)
    models = [model for found in by_provider.values() for model in found]
    if args.json:
        print(json.dumps([model.to_dict() for model in models], indent=2, ensure_ascii=False))
        return 0
    if not models:
        print("no free models matched the filters")
        return 0
    rows = []
    for model in models:
        days = model.days_until_expiry(date.today())
        rows.append(
            [
                model.provider,
                model.id,
                model.context_length,
                "yes" if model.supports_tools else "no",
                days if days is not None else "-",
            ]
        )
    _print_table(["PROVIDER", "MODEL", "CONTEXT", "TOOLS", "EXPIRES_IN_DAYS"], rows)
    counts = ", ".join(f"{len(found)} from {name}" for name, found in by_provider.items())
    print(f"\n{len(models)} free model(s): {counts}")
    return 0


def _ordered(config: Config, providers: Providers) -> Tuple[Dict[str, List[ModelInfo]], List[ModelInfo]]:
    by_provider = {
        name: _static_order(found, config.ranking.weights)
        for name, found in _discover_by_provider(config, providers).items()
    }
    merged = _static_order([m for found in by_provider.values() for m in found], config.ranking.weights)
    return by_provider, merged


def _cmd_test(args: argparse.Namespace, config: Config, providers: Providers) -> int:
    by_provider, models = _ordered(config, providers)
    results, _quotas = _probe_all(config, providers, by_provider, max_tests=args.max_tests)

    rows = []
    for model in models:
        test = results.get(model.key)
        rows.append(
            [
                _status(test),
                model.provider,
                model.id,
                f"{test.ttft_ms:.0f}" if test is not None and test.ttft_ms else "-",
                (test.error or "") if test is not None else "not probed (budget/cap)",
            ]
        )
    if rows:
        _print_table(["STATUS", "PROVIDER", "MODEL", "TTFT_MS", "ERROR"], rows)
    else:
        print("no free models matched the filters")
    return EXIT_ACCOUNT_ERROR if results.account_problem else 0


def _cmd_rank(args: argparse.Namespace, config: Config, providers: Providers) -> int:
    by_provider, models = _ordered(config, providers)
    results, quotas = _probe_all(config, providers, by_provider, no_probe=args.no_probe)
    ranked = rank(models, results, config.ranking.weights, today=date.today())
    selection = select(
        ranked,
        config.ranking.fallback_count,
        allow_untested=config.ranking.fallbacks_allow_untested,
    )
    payload = _ranking_payload([name for name, _ in providers], ranked, selection, quotas)

    output = args.output or config.output.ranking_json
    if output:
        _write_json(Path(output), payload)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if ranked:
        rows = []
        for index, item in enumerate(ranked, start=1):
            rows.append(
                [
                    index,
                    f"{item.score:.2f}",
                    item.model.provider,
                    item.model.id,
                    _status(item.test),
                    "; ".join(item.reasons) or "-",
                ]
            )
        _print_table(["RANK", "SCORE", "PROVIDER", "MODEL", "STATUS", "REASONS"], rows)
    else:
        print("no free models matched the filters")

    for name, quota in quotas.items():
        if quota is not None:
            line = f"\nquota ({name}): free_tier={quota.is_free_tier} daily_free_limit={quota.daily_free_limit}"
            if quota.daily_free_used is not None or quota.daily_free_remaining is not None:
                line += f" used={_dash(quota.daily_free_used)} remaining={_dash(quota.daily_free_remaining)}"
                line += f" (before this run's {quota.probes_since_read} probe(s)"
                if quota.remaining_estimate is not None:
                    line += f", about {quota.remaining_estimate} left now"
                line += "; data may lag)"
            print(line)
    if selection is not None:
        print(
            f"selection: {selection.primary.model.key} "
            f"(fallbacks: {_fallback_list(selection)})"
        )
    else:
        print("selection: none (no working model)")
    if output:
        print(f"ranking JSON written to {output}")
    return 0


def _apply_target(
    target: TargetConfig,
    selection: Selection,
    *,
    dry_run: bool,
    config: Optional[Config] = None,
) -> Any:
    """Apply *selection* to one target.

    ``options.keep_backups`` / ``options.backup_dir`` override the global
    ``backups`` section for this target.
    """

    options = dict(target.options)
    options.pop("providers", None)
    keep = options.pop("keep_backups", config.backups.keep if config else 5)
    backup_dir = options.pop("backup_dir", config.backups.dir if config else None)
    adapter_class = get_adapter_class(target.adapter)
    adapter = adapter_class(str(target.path), **options)
    return adapter.apply(
        selection,
        dry_run=dry_run,
        keep_backups=int(keep),
        backup_dir=Path(backup_dir).expanduser() if backup_dir else None,
    )


def _target_selection(config: Config, target: TargetConfig, ranked: Sequence[Any]) -> Optional[Selection]:
    """Select within the providers a target allows (``options.providers``)."""

    allowed = target.options.get("providers")
    if allowed:
        ranked = [item for item in ranked if item.model.provider in allowed]
    return select(
        ranked,
        config.ranking.fallback_count,
        allow_untested=config.ranking.fallbacks_allow_untested,
    )


def _cmd_sync(args: argparse.Namespace, config: Config, providers: Providers) -> int:
    by_provider, models = _ordered(config, providers)
    no_probe = args.no_probe or (args.dry_run and not args.probe)
    results, _quotas = _probe_all(config, providers, by_provider, no_probe=no_probe)
    ranked = rank(models, results, config.ranking.weights, today=date.today())
    selection = select(
        ranked,
        config.ranking.fallback_count,
        allow_untested=config.ranking.fallbacks_allow_untested,
    )

    if selection is None:
        if results.account_problem:
            print(
                "no usable model: probing was stopped by an account/quota problem "
                "(models were not marked as failed); no config was written",
                file=sys.stderr,
            )
            return EXIT_ACCOUNT_ERROR
        print("no usable model found; no config was written", file=sys.stderr)
        if no_probe:
            print(
                "hint: this run used cached probe results only (--dry-run/--no-probe); "
                "run `freemodel-sync test` first, or use `sync --dry-run --probe`",
                file=sys.stderr,
            )
        return 2

    print(f"selection: {selection.primary.model.key} (fallbacks: {_fallback_list(selection)})")

    failed_targets: List[str] = []
    succeeded: Dict[str, str] = {}
    if not config.targets:
        print("no targets configured; nothing to write")
    for target in config.targets:
        target_selection = _target_selection(config, target, ranked)
        if target_selection is None:
            failed_targets.append(f"{target.adapter}:{target.path}")
            print(
                f"error: {target.adapter} ({target.path}): no usable model from its providers "
                f"{', '.join(target.options.get('providers') or [])}; not written",
                file=sys.stderr,
            )
            continue
        if target_selection.primary.model.key != selection.primary.model.key:
            print(f"{target.adapter}: selection {target_selection.primary.model.key} (target providers)")
        try:
            result = _apply_target(target, target_selection, dry_run=args.dry_run, config=config)
        except Exception as exc:  # noqa: BLE001 - report and continue other targets
            failed_targets.append(f"{target.adapter}:{target.path}")
            print(f"error: {target.adapter} ({target.path}): {exc}", file=sys.stderr)
            continue
        succeeded[f"{target.adapter}:{target.path}"] = target_selection.primary.model.key
        action = "would update" if args.dry_run and result.changed else (
            "updated" if result.written else "unchanged"
        )
        print(f"{target.adapter}: {action} {result.path}")
        if args.dry_run and result.diff:
            print(result.diff)

    state_path = Path(config.state_path)
    previous = _read_state(state_path)
    old_key = previous.get("primary") or previous.get("key")
    new_key = selection.primary.model.key
    changed = old_key != new_key

    if failed_targets:
        # Do not advance the recorded primary or announce a switch that did
        # not fully happen: the next run retries and notifies once all
        # targets are written.
        print(
            f"error: {len(failed_targets)} target(s) failed; state not advanced, "
            "no notification sent",
            file=sys.stderr,
        )
        if not args.dry_run and succeeded:
            try:
                _write_partial_state(state_path, previous, succeeded)
            except OSError as exc:
                print(f"error: could not write state file {state_path}: {exc}", file=sys.stderr)
        return 1

    failures = 0
    if changed and not args.dry_run and not args.no_notify:
        channels = notify_switch(
            old_key if isinstance(old_key, str) else None,
            selection,
            telegram=config.notify.telegram,
            webhook=config.notify.webhook,
        )
        if channels:
            print(f"notified: {', '.join(channels)}")

    if not args.dry_run:
        try:
            _write_state(state_path, selection, succeeded)
        except OSError as exc:
            print(f"error: could not write state file {state_path}: {exc}", file=sys.stderr)
            failures += 1

    if failures:
        return 1
    return 0


def _cmd_providers(args: argparse.Namespace, config: Config) -> int:
    for name in available_providers():
        print(name)
    return 0


def _cmd_adapters(args: argparse.Namespace, config: Config) -> int:
    for name in available_adapters():
        print(name)
    return 0


# ---------------------------------------------------------------------------
# parser / entry point
# ---------------------------------------------------------------------------
class RedactingFilter(logging.Filter):
    """Mask secrets that can appear in log messages (e.g. Telegram bot URLs)."""

    _PATTERNS = (
        (re.compile(r"(api\.telegram\.org/bot)[^/\s\"']+"), r"\1<redacted>"),
        (re.compile(r"(?i)(bearer\s+)[^\s\"']+"), r"\1<redacted>"),
        (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "sk-<redacted>"),
    )

    @classmethod
    def redact(cls, text: str) -> str:
        for pattern, replacement in cls._PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = self.redact(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


_LOG_HANDLER: Optional[logging.Handler] = None


def _configure_logging(verbose: bool, debug_http: bool = False) -> None:
    """Install one stderr handler with secret redaction.

    ``httpx``/``httpcore`` log full request URLs at INFO/DEBUG, and Telegram
    puts the bot token in the URL, so they stay at WARNING unless
    ``--debug-http`` is given (and even then messages are redacted).
    """

    global _LOG_HANDLER
    root = logging.getLogger()
    if _LOG_HANDLER is not None:
        root.removeHandler(_LOG_HANDLER)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    _LOG_HANDLER = handler
    root.setLevel(logging.DEBUG if verbose else logging.WARNING)
    http_level = logging.DEBUG if (verbose and debug_http) else logging.WARNING
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(http_level)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser (exposed for tests and ``--help``)."""

    parser = argparse.ArgumentParser(
        prog="freemodel-sync",
        description=(
            "Discover, test and rank free LLMs, then sync a primary model plus "
            "fallbacks into the configs of tools you already use."
        ),
    )
    parser.add_argument(
        "-c", "--config", metavar="CONFIG", help="path to the YAML config file"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable verbose logging"
    )
    parser.add_argument(
        "--debug-http",
        action="store_true",
        help="also log HTTP requests (secrets in URLs are redacted)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    discover = subparsers.add_parser("discover", help="list free models after filters")
    discover.add_argument("--json", action="store_true", help="print JSON")

    test = subparsers.add_parser("test", help="discover, filter and probe models")
    test.add_argument("--max-tests", type=int, default=None, metavar="N", help="maximum probes")

    rank_parser = subparsers.add_parser("rank", help="rank models and show the selection")
    rank_parser.add_argument("--json", action="store_true", help="print JSON")
    rank_parser.add_argument("--output", metavar="FILE", help="write the ranking JSON to FILE")
    rank_parser.add_argument(
        "--no-probe", action="store_true", help="use cached probe results only; send no requests"
    )

    sync = subparsers.add_parser("sync", help="write the selection into all targets")
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="show diffs only: no target/state/cache writes, no probes (uses cached results)",
    )
    sync.add_argument(
        "--no-probe", action="store_true", help="use cached probe results only; send no requests"
    )
    sync.add_argument(
        "--probe", action="store_true", help="with --dry-run: probe as usual (spends quota, updates cache)"
    )
    sync.add_argument("--no-notify", action="store_true", help="do not send notifications")

    subparsers.add_parser("providers", help="list registered providers")
    subparsers.add_parser("adapters", help="list registered adapters")

    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    provider_factory: Optional[ProviderFactory] = None,
    *,
    config: Optional[Config] = None,
) -> int:
    """Run the CLI and return a process exit code.

    Args:
        argv: argument list (defaults to ``sys.argv[1:]``).
        provider_factory: optional ``factory(name, api_key=..., **options)``
            used instead of the registered provider class (for tests).
        config: pre-built :class:`Config` (skips loading a file).
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose, args.debug_http)

    if not args.command:
        parser.print_help()
        return 0

    try:
        if config is None:
            config = load_config(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "providers":
        return _cmd_providers(args, config)
    if args.command == "adapters":
        return _cmd_adapters(args, config)

    try:
        providers = _resolve_providers(config, provider_factory)
    except (ConfigError, ProviderError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "discover":
            return _cmd_discover(args, config, providers)
        commands = {"test": _cmd_test, "rank": _cmd_rank, "sync": _cmd_sync}
        if args.command in commands:
            with RunLock(Path(str(config.state_path) + ".lock")):
                return commands[args.command](args, config, providers)
    except LockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOCKED
    except (ConfigError, ProviderError, ValueError, OSError, MissingKeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - the CLI reports errors instead of tracebacks
        logger.debug("command failed", exc_info=True)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
