# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Shared rules in `spec/` (spec_version 1):** `providers.json` (OpenRouter and Groq: base URL,
  key variable, free rule, catalogue fields, probe request, error classification, rate-limit
  headers, key formats, sources), `ranking.json` (default weights, score constants, non-chat
  globs), JSON Schemas for both and for the golden cases in `spec/conformance/` (classification,
  stream errors, OpenRouter's free rule, rate-limit headers, scores and rank order, non-chat
  filter). The Python package now reads these constants and the error tables from the spec
  (`freemodel_sync.spec`; the wheel ships them), and `tests/test_spec_conformance.py` runs every
  case. No behaviour change: all existing tests pass unchanged and the cases were checked against
  the previous code. The dsh plugin will run the same cases.
- **Secret guard:** a `secret scan (gitleaks)` CI job (gitleaks pinned by version and SHA-256)
  with `.gitleaks.toml`, which adds rules for OpenRouter `sk-or-v1-`, Groq `gsk_`, `sk-` + 32
  (SenseNova and others) and Bailian/DashScope `sk-ws-`/`sk-sp-` keys to gitleaks' defaults. Pull
  requests scan their own commits, pushes to `main` the history. A test also checks that
  `examples/`, `docs/`, `spec/`, `plugins/` and the top-level documents contain no key-shaped
  strings.

- **Python 3.14** is supported and tested.
- **`Provider.close()` and context-manager support** (`with OpenRouterProvider() as p: ...`). A
  provider closes the HTTP client it created; a client passed in by the caller is left open. The
  CLI and the daily snapshot script now close their providers when they finish, so library and
  script use no longer leaks connections.
- **CI on Windows and macOS** (Python 3.10 and 3.14), next to the Linux matrix.
- **Type checking:** CI runs mypy on `src/` (a lenient configuration to start with), backing the
  `py.typed` marker the package already ships.

### Changed

- **Redaction** is shared by the CLI logger and the daily snapshot script
  (`freemodel_sync.redact`). The CLI now also masks the exact API key values it read from the
  environment, whatever their format, and the key patterns cover `sk-ws-`/`sk-sp-` keys
  containing `.` (before, the part after the first `.` survived) and `gsk_` keys in CLI logs.

- **`filters.include` / `filters.exclude` globs are case-insensitive**, like the built-in non-chat
  list. `"*qwen*"` now also matches `Qwen/Qwen3-Coder:free`; before, include/exclude used
  case-sensitive matching while the non-chat list did not.
- **Non-chat filter:** "guard" only matches as its own word or id segment (`llama-guard-4`,
  `prompt-guard`, "Llama Guard", `*guardrail*`). The old `*guard*` also dropped chat models
  whose name merely contains it, e.g. `guardian` or `vanguard`.
- **Daily snapshot workflow:** the job that runs the probes now has a read-only token and uploads
  the snapshot as an artifact; a separate `push` job, which runs no project code, is the only
  one with `contents: write` and commits it to the `data` branch.
- **Release workflow:** runs only in `ndwlbj/freemodel-sync` (forks cannot try to publish), and
  runs the test suite on the tagged commit before building.
- **Development:** ruff and mypy are pinned once, in the `dev` extra (the second ruff pin in CI is
  gone); the CI build job pins `build`/`twine` like the release workflow; ruff also checks
  `BLE` (blind `except Exception`) and `RUF100` (unused `noqa`); coverage is measured with branch
  coverage and now includes `scripts/` (threshold raised from 80% to 85%); an autouse test fixture
  blocks network access and hides real API keys, so a test with a missing mock fails instead of
  sending real requests.
- **Documentation of existing behaviour** (no behaviour change). The README and README.zh-CN now
  cover these points:
  - the limits of the run lock;
  - `backups.keep: 0` leaving existing backups in place;
  - AstrBot files being re-indented when the model changes;
  - zero-priced models without `:free` not being used;
  - `testing.timeout_s` applying to probes only;
  - how probe cache files are bound to the provider order;
  - the per-provider `daily_free_limit`;
  - checking the date of the daily snapshot, which goes stale if the maintainer's key fails or
    GitHub disables the schedule after 60 days without activity.

  `docs/providers.md` describes the `openrouter/*` meta-router exclusion, the quota lag and the
  fixed discovery timeout. The example config lists the per-target options `providers`,
  `keep_backups` and `backup_dir`, the `openai-yaml` option `preserve_comments`, and the `dsh`
  options `provider_name`, `entry_name` and `check_model`.
- **`sync --dry-run` help** no longer contradicts `--probe`: a dry run makes no probes and writes no
  cache unless `--probe` is given.
- **CHANGELOG:** 0.1.0 was never tagged or published, so its broken release and compare links are
  gone; `[0.2.0]` links to the v0.2.0 release.
- **Internal: shared OpenAI-compatible provider base.** The streaming probe, HTTP client handling
  and the failure-classification and rate-limit hooks moved from `providers/openrouter.py` into a
  new `providers/openai_compat.py` (`OpenAICompatProvider`). `OpenRouterProvider` and
  `GroqProvider` both subclass it now; Groq no longer inherits from OpenRouter. No change in
  behaviour: requests, classification rules and results are the same. This is groundwork for
  further OpenAI-compatible providers.

### Removed

- **Python 3.9 support.** `requires-python` is now `>=3.10`; 0.3.3 is the last release that
  installs on 3.9. This is the change announced as planned for 0.3.0, which had been deferred
  until now.

### Fixed

- **Daily snapshot: a failed provider no longer produces a misleading public report.** When model
  discovery failed for one provider (for example Groq), the run still wrote and committed
  `latest.json`/`latest.md` without that provider and listed all its models as "Removed". Such a
  snapshot is now marked `"partial": true` with `failed_providers`, its diff does not count that
  provider's models as removed, only the dated file is written (`latest.*` keep the last complete
  snapshot), the Markdown has a banner, and the next day's diff compares with the last complete
  snapshot. When discovery fails for every provider, nothing is written and the exit code is 1.
- **Daily snapshot files are written atomically** (`atomic_write_text`), so an interrupted run
  cannot leave a truncated `latest.json` or a JSON and Markdown that disagree. The files keep mode
  0644.
- **Daily snapshot: expired models are no longer probed** and no longer listed as "expiring soon"
  with a negative number of days. Their ids are recorded under the provider as `expired`.
- **Catalog watch fails the run whenever it finds an anomaly**, also with `--open-issue`. It used
  to exit 0 after opening the issue, so the scheduled run and its badge stayed green during a real
  schema change.
- **Catalog watch notices a collapse of the free catalog.** The default `--min-free` is now 5
  (was 1, so a drop from 16 free models to 2 was not reported), and the issue fingerprint includes
  the free-model count in buckets of 5, so a further drop while the issue is open is posted again.
  Expired free models are listed separately instead of as expiring in "-N days".
- **Windows: the run lock works.** `test`, `rank` and `sync` used to skip locking entirely on
  Windows (no `fcntl`), so overlapping runs probed twice and exit code 4 never happened there. The
  lock now uses `msvcrt.locking` on Windows; like `flock` on POSIX it is released by the operating
  system if the process dies.
- **Windows: backups are byte-for-byte copies.** The backup file was opened in Windows' default
  text mode, so every line ending in the copy gained an extra carriage return.

### Security

- **Log redaction covers tracebacks.** Secrets (Telegram bot URLs, bearer tokens, `sk-` keys) were
  only masked in the log message itself; a traceback logged with `-v` (`exc_info`) was added
  later by the formatter and was not redacted. Redaction now runs on the fully formatted record.

## [0.3.3] - 2026-10-26

### Fixed

- **A stream that ends with `finish_reason: "error"` is no longer a successful probe.** Without a
  separate `error` object, such a stream was counted as working (and could be selected and written
  to your configs). It is now a transient failure; `finish_reason: "content_filter"` is a model
  failure. `stop`, `length` and `tool_calls` are unchanged. (#21)
- **`"error": null` in a normal stream chunk no longer fails a healthy model.** Only a non-empty
  `error` value counts; before, the key alone marked the model temporarily unavailable with the
  message `None`. (#21)
- **OpenRouter 403 with only `metadata.provider_name`** is an account error again. `provider_name`
  is ordinary routing metadata, so on its own it no longer turns a 403 into a model failure (which
  let probing continue, and spend quota, on an account-level block). Routing or moderation metadata
  (`reasons`, `model_slug`, `failed_routing_step`, ...) still marks a 403 as model-specific. (#21)
- **Errors inside the stream follow the provider's own rules.** A Groq `498` (flex capacity) that
  arrives after HTTP 200 is transient, as it is before the stream, instead of a model failure
  cached for hours; a Groq in-stream `403` is an account error. (#21)
- **Probes have a total time limit.** `testing.timeout_s` is httpx's per-read timeout, which every
  keep-alive comment resets, so a model that never answered could hold a run for a long time. A
  stream that sends no token within twice `timeout_s` is now a transient failure. (#21)
- **Every OpenRouter price field must be zero.** A `:free` model with a non-zero `request`, `image`,
  `input_cache_read` or any other price field (or an unparseable one) is treated as paid and
  skipped; only `prompt` and `completion` were checked before. (#21)
- **`X-RateLimit-Reset`**: a relative value above 3600 is read as milliseconds (with a warning)
  instead of seconds, so `30000` pauses probing for 30 seconds, not 8 hours. Every pause taken from
  `Retry-After` or `X-RateLimit-Reset` is capped at 24 hours. (#21)
- **`X-RateLimit-Remaining: "0.0"`** (an integral decimal) is now understood, so the
  `reserve_requests` guard applies; such values were ignored before. (#21)
- An error response whose body cannot be read is classified by its status code instead of raising
  `ResponseNotRead` out of the probe. (#21)

### Changed

- **`openai-yaml` without ruamel.yaml no longer rewrites a file it would damage.** PyYAML re-dumps
  the whole document, which dropped comments and silently re-typed unrelated values (`1.10` became
  `1.1`, `yes` became `true`, `0755` became `493`). With the default `preserve_comments: auto`, such
  a file is now refused: the target fails and the file is left unchanged. Install the
  `yaml-comments` extra, or set `preserve_comments: false` to accept the re-dump. A file that
  PyYAML writes back as is, including one freemodel-sync already wrote this way, is still updated. (#22)
- **`dsh` refuses files it cannot edit in place.** A flow-style list (`[{id: ...}, ...]`) used to
  be re-dumped without its comments and with no warning. Two entries with the managed id used to
  get only the first one updated. Both now fail the target and leave the file unchanged. A file
  that only has comments now keeps them above the new entry. (#22)
- **`testing.max_tests` and `test --max-tests` must be at least 1.** `0` or a negative value used
  to send no request and still exit 0. The same applies to `daily_snapshot.py --max-probes` and
  `SNAPSHOT_MAX_PROBES`. A library call to `run_tests(max_tests=0)` now sets `stop_reason`. (#22)
- **Unknown keys inside config sections** (for example `testing.max_test` or
  `notify.telegram.chat_env`) are logged as a warning; `load_config(strict=True)` rejects them.
  Before, only unknown top-level keys were noticed, and only in strict mode. (#22)
- **One parser for on/off options.** `notify.<channel>.enabled`, `check_model` and
  `preserve_comments` accept `true/false`, `yes/no`, `on/off` and `1/0` (quoted or not). Any other
  value is an error. Before, `enabled: "false"` left a channel on, and `check_model: "off"` kept
  the check on. (#22)
- **`rank` exits with 3** when an account or quota problem stopped probing, as `test` does. It
  used to always exit 0. (#22)
- **Expired models are always dropped**, even with `exclude_expiring_within_days: null`. Before,
  they could be probed or selected and were shown as "expires in -N days". The daily snapshot
  still lists them. (#22)
- **No more silent setup mistakes:**
  - A configured Telegram or webhook channel whose environment variables are not set now logs a
    warning instead of an INFO message, which the default log level hid.
  - Creating a target file that does not exist logs a warning.
  - `sync` without targets says that it still records and announces the selection. (#22)
- **The example config ships with its targets and notification channels commented out**, so
  copying it no longer creates files at placeholder paths. An empty `notify:` section is now
  accepted. (#22)

## [0.3.2] - 2026-10-24

### Fixed

- **dsh adapter** checks the selected model before writing: when the same `cordis.patch.yml` declares
  the target provider's `models` list (dsh's `llm-pi-ai` entry), a model that is not in it is refused
  with an error and the file is left unchanged (the target counts as failed, like other adapter
  errors). Providers without a `models` list in the file are not checked. New target option
  `check_model: false` disables the check. (#14)
- **OpenRouter quota figures that lag behind real usage.** `free_model_daily_requests` is read once
  from `/api/v1/key` before probing, so the reported `used`/`remaining` never included the run's own
  probes, and OpenRouter's `used` counter can also trail requests that were already sent (one
  snapshot read `used: 7` and then sent 11 probes; the next one, hours later, read `used: 11`). Now:
  - the probing budget uses this tool's own probe count for the UTC day when it is higher than the
    reported `used`, so a lagging counter cannot eat into `reserve_requests`;
  - `rank` prints `used`/`remaining` with "before this run's N probe(s), about M left now; data may
    lag", and the ranking JSON quota gains `probes_since_read`, `remaining_estimate` and `note`;
  - the daily snapshot marks its quota as `"read": "before probing"`, adds `remaining_estimate` and
    a note, and the Markdown table says the counters may lag. (#15)
- **Mid-stream rate limits no longer stop probing.** An error event that arrives inside the SSE
  stream, after HTTP 200 (for example "... is temporarily rate-limited upstream", a mid-stream `429`
  or a provider `5xx`), is now a transient failure of that model: it is cached briefly and the next
  model is probed. Before, a mid-stream `429` without provider metadata counted as an account/quota
  error and ended the round (the 2026-10-23 snapshot stopped after 11 of 15 probes this way).
  Platform limits are enforced before the stream starts, so pre-stream classification is unchanged
  (a platform `429`, `401`, `402` and account-level `403` still stop probing); in the stream only an
  explicit `401`/`402` or account-level `403` code still does. Applies to Groq as well. (#17)
- README (English and Chinese): the probing notes no longer say every 403 stops the round. A 403
  with model-specific metadata (routing/moderation details) is a failure of that model and probing
  continues; other 403s are account problems and stop the round, as the code already did. The same
  paragraph now also lists 408 as transient, says that in the stream only an explicit `401`/`402` or
  account-level `403` stops probing, that other errors such as 400/404 are model failures, and that
  Groq treats every 401/403/429 as an account problem. (#18)

### Changed

- Code formatted with `ruff format` (formatting only, no logic changes). CI now also runs
  `ruff format --check src tests scripts`, and ruff is pinned to `0.17.2` both in CI and in the
  `dev` extra (was `ruff>=0.4`), so a new ruff release cannot break CI on its own. The development
  commands in README, README.zh-CN and CONTRIBUTING include `scripts` and the format check. (#19)
- README (English and Chinese): the daily snapshot section is now **Daily health check**, with
  the schedule (01:17 UTC, about 09:17 Beijing time; GitHub may start it late), the 15-models-per-
  provider probe cap, the Groq condition and links to the public `data` branch snapshots. (#16)
- Daily free-model snapshot cron moved from `0 1 * * *` (01:00 UTC) to `17 1 * * *` (01:17 UTC)
  to avoid the usual GitHub Actions on-the-hour queue. (#13)

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

Never tagged or published to PyPI; 0.2.0 is the first published release.

- Initial version: OpenRouter discovery, budget-aware probing, ranking, and the
  `openai-env`, `openai-yaml`, `dsh` and `astrbot` adapters, plus Telegram/webhook notifications.

[Unreleased]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/ndwlbj/freemodel-sync/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/ndwlbj/freemodel-sync/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ndwlbj/freemodel-sync/releases/tag/v0.2.0
