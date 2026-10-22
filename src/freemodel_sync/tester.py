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
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from .models import ModelInfo, TestResult
from .providers.base import Provider


class ResultCache:
    """A JSON-backed cache of :class:`TestResult` objects plus a daily counter.

    File layout::

        {
          "openrouter|vendor/model:free": {"key": ..., "ok": true, ...},
          "daily": {"date": "YYYY-MM-DD", "count": 3}
        }

    Missing or corrupt files are treated as an empty cache.
    """

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self.path: Optional[Path] = Path(path).expanduser() if path else None
        self._results: Dict[str, TestResult] = {}
        self._daily_date: Optional[str] = None
        self._daily_count: int = 0

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
            if key == "daily":
                continue
            if not isinstance(value, dict):
                continue
            try:
                result = TestResult.from_dict(value)
            except (TypeError, ValueError):
                continue
            results[key] = result
        self._results = results

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
    def get(self, key: str, max_age_s: float) -> Optional[TestResult]:
        """Return a fresh cached result for ``key`` (marked ``cached=True``)."""

        result = self._results.get(key)
        if result is None:
            return None
        age = time.time() - result.tested_at
        if age > max_age_s:
            return None
        # Return a copy so marking it cached does not mutate the stored entry.
        data = result.to_dict()
        data["cached"] = True
        return TestResult.from_dict(data)

    def put(self, result: TestResult) -> None:
        """Store a result (does not write the file; call :meth:`save`)."""

        self._results[result.key] = result

    # -- daily request counter ------------------------------------------
    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

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


def run_tests(
    provider: Provider,
    models: Iterable[ModelInfo],
    *,
    cache: ResultCache,
    max_tests: int = 5,
    cache_ttl_s: float = 6 * 3600,
    daily_budget: Optional[int] = None,
    timeout: float = 30.0,
    reserve: int = 10,
) -> Dict[str, TestResult]:
    """Probe models in order, reusing fresh cache entries and respecting budgets.

    Returns a mapping ``model.key -> TestResult``.  Models that were neither
    cached nor tested are simply absent from the result.
    """

    results: Dict[str, TestResult] = {}
    tests_done = 0

    for model in models:
        cached = cache.get(model.key, cache_ttl_s)
        if cached is not None:
            results[model.key] = cached
            continue

        if tests_done >= max_tests:
            continue
        if daily_budget is not None and cache.requests_today() + 1 + reserve > daily_budget:
            continue

        try:
            result = provider.test(model, timeout=timeout)
        except Exception as exc:  # providers normally catch their own errors
            result = TestResult(
                key=model.key,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                tested_at=time.time(),
            )
        finally:
            # Every probe that was actually attempted counts, even if the
            # provider raised an unexpected exception.
            cache.add_requests(1)
        cache.put(result)
        results[model.key] = result
        tests_done += 1

    cache.save()
    return results
