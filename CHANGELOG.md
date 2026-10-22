# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/ghwghw19/freemodel-sync/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ghwghw19/freemodel-sync/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ghwghw19/freemodel-sync/releases/tag/v0.1.0
