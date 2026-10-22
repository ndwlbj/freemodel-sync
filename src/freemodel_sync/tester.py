"""Probe free models with tiny requests and cache the results.

The cache is a single JSON file so repeated CLI invocations do not burn the
provider's (small) daily free-model quota.  It also tracks how many probe
requests were made today, which lets the caller stop before exhausting the
provider budget.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from .models import ModelInfo, TestResult
from .providers.base import Provider

_RESERVED_KEYS = {"daily", "blocked_until"}


class ResultCache:
    """A JSON-backed cache of :class:`TestResult` objects plus a daily counter.

    File layout::

        {
          "openrouter|vendor/model:free": {"key": ..., "ok": true, ...},
          "daily": {"date": "YYYY-MM-DD", "count": 3},
          "blocked_until": 1767225600.0
        }

    ``daily`` counts probes per **UTC** day (the day boundary OpenRouter uses
    for free-model limits).  ``blocked_until`` is set after an account-level
    rate limit so later runs do not probe before the provider's reset time.
    Missing or corrupt files are treated as an empty cache.
    """

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path: Optional[Path] = Path(path).expanduser() if path else None
        self._results: Dict[str, TestResult] = {}
        self._daily_date: Optional[str] = None
        self._daily_count: int = 0
        self.blocked_until: float = 0.0

    # -- persistence -----------------------------------------------------
    def load(self, path: Optional[Union[str, Path]] = None) -> ResultCache:
        """Load results from ``path`` (or the instance path); never raises."""

        if path is not None:
            self.path = Path(path).expanduser()
        if self.path is None:
            return self
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return self
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return self
        if not isinstance(payload, dict):
            return self

        results: Dict[str, TestResult] = {}
        for key, value in payload.items():
            if key in _RESERVED_KEYS:
                continue
            if not isinstance(value, dict):
                continue
            try:
                result = TestResult.from_dict(value)
            except (TypeError, ValueError):
                continue
            results[key] = result
        self._results = results

        try:
            self.blocked_until = float(payload.get("blocked_until") or 0.0)
        except (TypeError, ValueError):
            self.blocked_until = 0.0
        daily = payload.get("daily")
        if isinstance(daily, dict):
            daily_date = daily.get("date")
            self._daily_date = str(daily_date) if daily_date else None
            try:
                self._daily_count = max(0, int(daily.get("count") or 0))
            except (TypeError, ValueError):
                self._daily_count = 0
        return self

    def save(self) -> None:
        """Atomically write the cache, creating its parent directory if needed."""

        if self.path is None:
            raise ValueError("ResultCache has no path; call load(path) first")
        payload: Dict[str, Any] = {
            key: result.to_dict() for key, result in self._results.items()
        }
        payload["daily"] = {"date": self._today(), "count": self.requests_today()}
        if self.blocked_until > time.time():
            payload["blocked_until"] = self.blocked_until

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- result access ---------------------------------------------------
    def get(
        self, key: str, max_age_s: float, transient_max_age_s: Optional[float] = None
    ) -> Optional[TestResult]:
        """Return a fresh cached result for ``key`` (marked ``cached=True``).

        Transient failures (upstream 429, 5xx, timeouts) expire after
        ``transient_max_age_s`` when given, so a briefly saturated model is
        retried soon instead of being shunned for the full TTL.
        """

        result = self._results.get(key)
        if result is None:
            return None
        if result.is_account_error:
            return None  # never trust account-level failures (old caches)
        ttl = max_age_s
        if not result.ok and result.failure_kind == "transient" and transient_max_age_s is not None:
            ttl = min(ttl, transient_max_age_s)
        age = time.time() - result.tested_at
        if age > ttl:
            return None
        # Return a copy so marking it cached does not mutate the stored entry.
        data = result.to_dict()
        data["cached"] = True
        return TestResult.from_dict(data)

    def put(self, result: TestResult) -> None:
        """Store a result (does not write the file; call :meth:`save`).

        Account-level failures are ignored: they are not about the model.
        """

        if result.is_account_error:
            return
        self._results[result.key] = result

    # -- daily request counter ------------------------------------------
    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def requests_today(self) -> int:
        """Number of probe requests recorded for today."""

        if self._daily_date != self._today():
            return 0
        return self._daily_count

    def add_requests(self, n: int = 1) -> None:
        """Record ``n`` probe requests, resetting the counter on a new day."""

        today = self._today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        self._daily_count += max(0, int(n))


class TestRun(dict):
    """Mapping ``model.key -> TestResult`` plus information about the round.

    Attributes:
        probes: number of requests actually sent in this round.
        stop_reason: why probing stopped early (``None`` if it did not), e.g.
            an account/quota error or the daily budget.
        account_error: the account-level failure that stopped the round, if any.
    """

    __test__ = False  # keep pytest from collecting this class

    def __init__(self) -> None:
        super().__init__()
        self.probes = 0
        self.stop_reason: Optional[str] = None
        self.account_error: Optional[TestResult] = None
        #: True when probing was skipped because an earlier rate limit has not reset
        self.rate_limited = False

    @property
    def account_problem(self) -> bool:
        """True when the round was cut short by the account, not by the models."""
        return self.account_error is not None or self.rate_limited


def run_tests(
    provider: Provider,
    models: Iterable[ModelInfo],
    *,
    cache: ResultCache,
    max_tests: int = 5,
    cache_ttl_s: float = 6 * 3600,
    transient_ttl_s: float = 30 * 60,
    daily_budget: Optional[int] = None,
    remaining_budget: Optional[int] = None,
    timeout: float = 30.0,
    reserve: int = 10,
) -> TestRun:
    """Probe models in order, reusing fresh cache entries and respecting budgets.

    Args:
        daily_budget: free requests per UTC day; checked against the local
            probe counter (used when the provider does not report usage).
        remaining_budget: free requests left today *as reported by the
            provider*; when given it is the source of truth.
        reserve: requests to leave untouched for the user's real traffic.

    Probing stops immediately, without caching anything for the affected
    model, on an account-level failure (bad key, no credits, platform rate
    limit), when ``X-RateLimit-Remaining`` drops to the reserve, or while a
    previous rate limit's reset time has not passed.  Models that were
    neither cached nor tested are simply absent from the result.
    """

    run = TestRun()
    allowed: Optional[int] = None
    if remaining_budget is not None:
        allowed = max(0, remaining_budget - reserve)
    elif daily_budget is not None:
        allowed = max(0, daily_budget - reserve - cache.requests_today())

    blocked = cache.blocked_until > time.time()
    if blocked:
        run.rate_limited = True
        run.stop_reason = "rate limited until " + datetime.fromtimestamp(
            cache.blocked_until, timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")

    for model in models:
        cached = cache.get(model.key, cache_ttl_s, transient_ttl_s)
        if cached is not None:
            run[model.key] = cached
            continue
        if run.stop_reason is not None:
            continue
        if run.probes >= max_tests:
            continue
        if allowed is not None and run.probes >= allowed:
            run.stop_reason = f"daily free-request budget reached (keeping {reserve} in reserve)"
            continue

        try:
            result = provider.test(model, timeout=timeout)
        except Exception as exc:  # providers normally catch their own errors
            result = TestResult(
                key=model.key,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                failure_kind="transient",
                tested_at=time.time(),
            )
        # Every probe that was actually sent counts, whatever its outcome.
        run.probes += 1
        cache.add_requests(1)

        if result.is_account_error:
            run.account_error = result
            run.stop_reason = f"account/quota error ({result.status_code or 'n/a'}): {result.error}"
            if result.retry_after_s:
                cache.blocked_until = time.time() + result.retry_after_s
            continue  # not cached, not part of the results

        cache.put(result)
        run[model.key] = result
        if result.rate_limit_remaining is not None and result.rate_limit_remaining <= reserve:
            run.stop_reason = (
                f"provider rate limit nearly exhausted (X-RateLimit-Remaining={result.rate_limit_remaining})"
            )
            if result.retry_after_s:
                cache.blocked_until = time.time() + result.retry_after_s

    if run.probes or blocked:
        cache.save()
    return run
