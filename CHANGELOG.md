# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

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

### Added

- Exit code `3`: probing was stopped by an account or quota problem.
- `testing.transient_ttl_minutes` and the `--debug-http` flag.

## [0.1.0] - 2026-10-22

- Initial release: OpenRouter discovery, budget-aware probing, ranking, and the
  `openai-env`, `openai-yaml`, `dsh` and `astrbot` adapters, plus Telegram/webhook notifications.
