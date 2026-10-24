# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **dsh adapter** checks the selected model before writing: when the same `cordis.patch.yml` declares
  the target provider's `models` list (dsh's `llm-pi-ai` entry), a model that is not in it is refused
  with an error and the file is left unchanged (the target counts as failed, like other adapter
  errors). Providers without a `models` list in the file are not checked. New target option
  `check_model: false` disables the check.
- **OpenRouter quota figures that lag behind real usage.** `free_model_daily_requests` is read once
  from `/api/v1/key` before probing, so the reported `used`/`remaining` never included the run's own
  probes, and OpenRouter's `used` counter can also trail requests that were already sent (one
  snapshot read `used: 7` and then sent 11 probes; the next one, hours later, read `used: 11`). Now:
  - the probing budget uses this tool's own probe count for the UTC day when it is higher than the
    reported `used`, so a lagging counter cannot eat into `reserve_requests`;
  - `rank` prints `used`/`remaining` with "before this run's N probe(s), about M left now; data may
    lag", and the ranking JSON quota gains `probes_since_read`, `remaining_estimate` and `note`;
  - the daily snapshot marks its quota as `"read": "before probing"`, adds `remaining_estimate` and
    a note, and the Markdown table says the counters may lag.

### Changed

- README (English and Chinese): the daily snapshot section is now **Daily health check**, with
  the schedule (01:17 UTC, about 09:17 Beijing time; GitHub may start it late), the 15-models-per-
  provider probe cap, the Groq condition and links to the public `data` branch snapshots.
- Daily free-model snapshot cron moved from `0 1 * * *` (01:00 UTC) to `17 1 * * *` (01:17 UTC)
  to avoid the usual GitHub Actions on-the-hour queue.

## [0.3.1] - 2026-10-23

### Added

- **Daily free-model snapshot** (repository automation, not part of the package): the
  `daily-snapshot.yml` workflow runs `scripts/daily_snapshot.py` every day at 01:00 UTC. It discovers
  the free models of OpenRouter (and Groq when `GROQ_API_KEY` is set and the `GROQ_PLAN` variable is
  `free`), probes at most 15 per provider within the reported free-request quota (account errors stop
  probing, as in `test`), and commits `snapshots/YYYY-MM-DD.json`, `latest.json` and `latest.md`, with
  the changes since the previous snapshot, to the orphan `data` branch. Error texts are redacted and the
  output is checked for key values before it is written.

### Fixed

- **OpenRouter 403 that only affects one model** (for example a free endpoint "only available
  on agentic harnesses", or a moderation flag) is now a failure of that model. It is cached like
  other model failures, and probing continues. In 0.3.0 every 403 counted as an account error, so
  probing stopped at that model on every run and the models after it were never tested. A 403
  with a budget `limit_source`, a guardrail block or no metadata is still an account error.
- `test`/`rank` tables show upstream 429/5xx/timeout failures as `transient` ("temporarily
  unavailable ... (retried later)") instead of `failed`.

### Changed

- **CI** runs the Python 3.9 jobs (the test matrix and the minimum-dependency job) on
  `ubuntu-24.04` instead of `ubuntu-latest`: Ubuntu 26.04 has no Python 3.9 build for
  `actions/setup-python`. Job names are unchanged.

## [0.3.0] - 2026-10-22

### Changed

- **Multiple providers (P2-3):** every enabled provider now feeds one ranking; previously
  only the first enabled provider was used. A `providers` section in your config *replaces*
  the default instead of being merged into it, so OpenRouter can be omitted or disabled.
  Each provider defaults to its own API key variable, and gets its own cache file
  (`<cache>.<provider>.json` for all but the first), daily counter and rate-limit pause.
  Fallbacks come from the primary's provider only.
- **Ranking JSON:** `provider` is replaced by `providers` (a list), and `quota` is now a
  mapping from provider name to quota. `discover`, `test` and `rank` tables gain a
  PROVIDER column.

### Added

- **Groq provider** (`groq`, `GROQ_API_KEY`). Groq's API has no prices, so it is used only
  after you confirm a Free-plan organization with `providers.groq.plan: free`. Handles
  Groq's RPD rate-limit headers and error codes. SiliconFlow was evaluated and not added
  because its API cannot show which models are free (see `docs/providers.md`).
- Target option `options.providers` limits a target to the providers its tool has a key
  for; a warning is logged when several providers are enabled and a target has none.
- Per-provider `daily_free_limit` override.
- **Comment-preserving YAML (P2-8):** with the optional extra
  `freemodel-sync[yaml-comments]` (ruamel.yaml) the `openai-yaml` adapter keeps comments,
  key order and quoting when it changes a value. Behaviour without the extra is unchanged.
  New target option `preserve_comments` (`auto` by default, `true` to require ruamel.yaml,
  `false` to always use PyYAML). CI installs the extra in the main test matrix.
- Dependabot (`.github/dependabot.yml`): weekly grouped update PRs for pip dependencies and
  for the SHA-pinned GitHub Actions.
- Release workflow (`.github/workflows/release.yml`) that publishes to PyPI with Trusted
  Publishing (no API token) when a GitHub release is published, or on demand for an existing
  tag. It fails if the tag does not match `__version__` and runs `twine check --strict`
  first. The maintainer steps are in `CONTRIBUTING.md`.

## [0.2.0] - 2026-10-22

### Changed

- **`sync --dry-run` is zero-cost:** it uses cached probe results only, sends no chat or
  `/key` request, needs no API key and writes no target, state or cache file. Use
  `--probe` to probe during a dry run. `rank` and `sync` gain `--no-probe`.
- **Fallbacks** contain only models that passed their probe. Set
  `ranking.fallbacks_allow_untested: true` for the old behaviour; such fallbacks are
  shown as `(untested)` and listed in `selection.untested_fallbacks`.
- **Non-chat models** (safety classifiers, guard/moderation, embedding, rerank, speech)
  are excluded by default (`filters.exclude_non_chat`).
- **Failed targets:** if any target cannot be written, `sync` exits `1`, does not advance
  the recorded primary and sends no notification; successful targets are recorded per
  target in the state file and the next run retries.
- **Backups** are rotated (newest 5 kept by default, `backups.keep`, per target
  `options.keep_backups`), can go to `backups.dir`, and are created with mode 0600 or
  stricter.
- **dsh adapter** (checked against dsh 0.2.1-rc.2, see `docs/dsh-verification.md`): keeps
  other keys in the managed entry's `config` (such as `reasoningEffort`) and its `name`;
  new `entry_name` option.

- **Probe size:** `max_tokens` defaults to 16 (was 8) and is configurable with
  `providers.openrouter.probe_max_tokens`.
- **Durable writes:** targets, cache and state are fsynced before being replaced and keep
  the original file's mode and, where permitted, owner and group.

### Deprecated

- **Python 3.9** reached end of life in October 2025. 0.2.x still supports it; 0.3.0 is
  planned to require Python 3.10 or newer.
- dsh `fallback_entry_id`: dsh rejects unknown patch ids, so the option is ignored with a
  warning. Remove any `freemodel-fallbacks` entry left in your `cordis.patch.yml`.

### Added

- `CONTRIBUTING.md`, `SECURITY.md`, issue and pull request templates.
- CI: SHA-pinned actions, minimum-dependency job, build + `twine check`, coverage floor.
- Daily `Catalog watch` workflow that checks OpenRouter's public model list without a key
  and opens a single deduplicated issue on anomalies.
- Exit code `3`: probing was stopped by an account or quota problem.
- Lock file next to the state file: overlapping `test`/`rank`/`sync` runs exit with the new
  code `4` instead of probing and writing twice.
- Warning when `notify.webhook.url` is stored in the config file, and a `chmod 600` hint
  when that file is readable by others.
- `py.typed` marker; PEP 639 license metadata, maintainer and Changelog URL.
- `testing.transient_ttl_minutes` and the `--debug-http` flag.

### Fixed

- **Time-based pricing:** a `:free` model with a non-zero price in `pricing.overrides` is
  no longer treated as free.
- README (English and Chinese): removed overclaims, absolute links for PyPI, documented
  `OPENAI_FALLBACK_MODELS` as non-standard.
- **Free quota:** the probe budget now comes from `free_model_daily_requests`
  (`used` / `limit` / `remaining`) in OpenRouter's `GET /api/v1/key` instead of being
  inferred from `is_free_tier`. A conservative 50/day is assumed when it is missing.
  The local probe counter resets per UTC day.
- **Account vs. model errors:** 401/402/403 and OpenRouter platform 429s stop probing
  after one request and are no longer cached as model failures. `Retry-After` and
  `X-RateLimit-Remaining`/`X-RateLimit-Reset` are honored. Upstream-provider 429s, 5xx
  and timeouts are cached only for `testing.transient_ttl_minutes` (default 30).
  Previously, an exhausted quota could send one probe per model and mark every model
  failed for 6 hours.
- **Missing API key:** `test`, `rank` and `sync` now exit with a clear error instead of
  caching every model as "missing api key" and counting the probes.
- **AstrBot:** support the `provider_sources` layout used since AstrBot v4.10.0 (the model
  goes in the provider entry's top-level `model`). Legacy `model_config.model` configs
  still work, and an unrecognized structure raises an error instead of silently doing nothing.
- **Logging:** `-v` no longer prints the Telegram bot token. httpx request logging is
  off unless `--debug-http` is given, and log records are redacted.
- **Symlinks:** a symlinked target file is no longer replaced by a regular file. The real
  file is backed up and updated.

## [0.1.0] - 2026-10-22

- Initial release: OpenRouter discovery, budget-aware probing, ranking, and the
  `openai-env`, `openai-yaml`, `dsh` and `astrbot` adapters, plus Telegram/webhook notifications.

[Unreleased]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ndwlbj/freemodel-sync/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ndwlbj/freemodel-sync/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ndwlbj/freemodel-sync/releases/tag/v0.1.0
