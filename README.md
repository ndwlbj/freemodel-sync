# freemodel-sync

[![CI](https://github.com/ndwlbj/freemodel-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/ndwlbj/freemodel-sync/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

[English](https://github.com/ndwlbj/freemodel-sync/blob/main/README.md) | [简体中文](https://github.com/ndwlbj/freemodel-sync/blob/main/README.zh-CN.md)

**Discover, test and rank free LLMs, then write the top-ranked working one (plus fallbacks) into the configs of tools you already use.**

Free LLM endpoints come and go: models get added, rate-limited, deprecated or quietly start
costing money. `freemodel-sync` points your bots and scripts at a free model that passed a
recent probe. It cannot guarantee the model keeps working between runs.

> **Not a proxy.** freemodel-sync never sees or forwards your traffic. It only edits config
> files (with a backup) and then gets out of the way. Your tools keep talking to the provider directly.

## How it works

```
discover ──► filter ──► probe (tiny, cached, budgeted) ──► rank ──► select ──► write configs ──► notify
```

1. **Discover** free models from the public OpenRouter catalogue
   (`GET /api/v1/models`, no key needed). A model counts as free only if its id ends in
   `:free`, prompt *and* completion prices are `0`, and it takes and returns text.
   The `openrouter/free` meta-router is excluded.
2. **Filter** by tool-calling support, minimum context window, id globs, and expiry:
   models whose `expiration_date` is within N days are dropped, and models expiring within
   30 days are penalised.
3. **Probe** each candidate with one tiny streaming request (`max_tokens: 16` by default, `providers.openrouter.probe_max_tokens`) using *your own*
   OpenRouter key, measuring availability and time-to-first-token. Probing is frugal:
   candidates are tried in order of promise, results are cached (6 h by default), at most
   `max_tests` new probes are made per run, and the round stops while keeping
   `reserve_requests` of the free requests left today, as reported by
   `free_model_daily_requests.remaining` in `GET /api/v1/key` (UTC day; per OpenRouter's documentation at the time of writing, 50/day below 10
   purchased credits and 1000/day above). If the key endpoint reports nothing, a conservative
   50/day is assumed against a local UTC-day counter.
   - **Account problems are not model failures.** A 401/402/403 or an OpenRouter platform 429
     (free-model per-minute/per-day cap) stops the round after that single request; the model is
     *not* cached as failed, and `Retry-After` / `X-RateLimit-Reset` pause later runs until the
     reset. Upstream-provider 429s, 5xx and timeouts count as transient failures and are retried
     after `transient_ttl_minutes` (30 by default).
   - Without an API key, `test`, `rank` and `sync` exit with an error and send nothing.
4. **Rank** with an explainable score (availability ≫ latency, context, tools, expiry).
   Fallbacks are models that passed their probe; untested models are used only if you set
   `ranking.fallbacks_allow_untested: true`, and are then marked `(untested)`. Non-chat models
   (safety classifiers, embedding, rerank, speech) are excluded by default.
5. **Write** the primary model and fallback list into each configured target. Every write is
   idempotent (unchanged → untouched), supports `--dry-run` with a diff, makes a timestamped
   `*.bak-*` backup (mode 0600 or stricter, the newest 5 kept by default; see `backups`) and
   replaces the file atomically. If no model passes its probe, **nothing is written**.
6. **Notify** (optional) via Telegram or a generic webhook when the primary model changes. If any
   target fails to write, the run exits `1`, the recorded state is not advanced and no notification
   is sent; the next run retries.

## Install

```bash
pipx install freemodel-sync              # latest release from PyPI
pipx install git+https://github.com/ndwlbj/freemodel-sync   # unreleased changes from main
# or run without installing
uvx --from git+https://github.com/ndwlbj/freemodel-sync freemodel-sync --help
# from a local checkout
pipx install .
```

Requires Python 3.9+ (Python 3.9 is end-of-life; a future release is planned to require 3.10+). Runtime dependencies: `httpx`, `PyYAML`.

## Quick start

```bash
export OPENROUTER_API_KEY=...            # your own key; only read from the environment
freemodel-sync discover                  # list free models (no key needed)
freemodel-sync test --max-tests 3        # probe the 3 most promising ones
freemodel-sync rank --json               # full ranking + selection as JSON
cp examples/config.example.yml ~/.config/freemodel-sync/config.yml   # then edit targets
freemodel-sync sync --dry-run            # show the diffs
freemodel-sync sync                      # write configs, notify on change
```

Run `sync` from cron or a systemd timer, e.g. every 3 hours. Keep the key out of the crontab:
put `export OPENROUTER_API_KEY=...` in a file only you can read (`chmod 600 ~/.config/freemodel-sync/env`)
and source it, or use `EnvironmentFile=` in a systemd unit.

```cron
0 */3 * * * . "$HOME/.config/freemodel-sync/env" && freemodel-sync sync >> "$HOME/.cache/freemodel-sync/sync.log" 2>&1
```

Exit codes: `0` success, `1` error (bad config, missing key, a target failed), `2` no usable model
(no file written), `3` probing was stopped by an account/quota problem such as a platform rate limit
or missing credits (no file written, no model marked as failed), `4` another run is still in progress
(`test`, `rank` and `sync` take a lock next to the state file, so overlapping cron runs never probe twice).

`sync --dry-run` is zero-cost: it uses only cached probe results (from an earlier `test`/`sync`), sends no chat or `/key` request, needs no API key, and writes no target, state or cache file. It still fetches the public model list. Add `--probe` to probe as usual during a dry run (this spends free-tier requests and updates the cache). `rank --no-probe` and `sync --no-probe` likewise use cached results only.

## Configuration

Default location: `~/.config/freemodel-sync/config.yml` (override with `-c FILE` or
`$FREEMODEL_SYNC_CONFIG`). Every key is optional; see
[`examples/config.example.yml`](https://github.com/ndwlbj/freemodel-sync/blob/main/examples/config.example.yml) for the full annotated file.

## Providers

| provider | key variable | free when | notes |
| --- | --- | --- | --- |
| `openrouter` (default) | `OPENROUTER_API_KEY` | `:free` id and every price (including `pricing.overrides`) is 0 | public model list, quota from `/api/v1/key` |
| `groq` | `GROQ_API_KEY` | your Groq organization is on the **Free plan**; confirm with `plan: free` | Groq's API has no prices; the model list needs the key |

Groq and multi-provider ranking need freemodel-sync 0.3.0 or newer. All enabled providers feed one ranking. The `providers` section replaces the default
(OpenRouter only), so you can drop OpenRouter or set `enabled: false`. Each provider uses its own
key variable, cache file, daily counter and rate-limit pause, and a quota problem stops probing only
for that provider. Fallbacks always come from the primary's provider. Restrict a target to the
providers its tool has a key for with `options.providers: [openrouter]`; otherwise its base URL may
switch provider. Details and sources are in [docs/providers.md](https://github.com/ndwlbj/freemodel-sync/blob/main/docs/providers.md).

```yaml
providers:
  openrouter: {}
  groq: {plan: free}          # only if your Groq org is on the Free plan
targets:
  - adapter: openai-env
    path: ~/bot/.env
    options: {providers: [openrouter]}   # this bot only has an OpenRouter key
```

## Targets (adapters)

| adapter | file | what it writes |
| --- | --- | --- |
| `openai-env` | `KEY=VALUE` env file | `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_FALLBACK_MODELS` (names configurable). `OPENAI_FALLBACK_MODELS` is not a standard variable: your tool must read it itself. Other lines, comments and your API key are left untouched. |
| `openai-yaml` | any YAML file | `base_url`, `model`, `fallback_models` under a dotted `key_path` (default `llm`). |
| `dsh` | dsh (DeepSeek Harness) `cordis.patch.yml`-style list | Replaces only the `agent-default-model` entry with `config: {provider: <p>, model: '<m>'}`; other entries and comments are kept byte-for-byte. Use `provider_map` to map `openrouter` to your dsh provider id. Other keys already in that entry's `config` (e.g. `reasoningEffort`) and its `name` are kept; `entry_name` sets the name. dsh has no fallback-list entry, so fallbacks are not written (`fallback_entry_id` is deprecated and ignored). If the same file declares the provider's `models` list (dsh's `llm-pi-ai` entry), a model missing from it is refused and nothing is written; `check_model: false` turns this off. |
| `astrbot` (experimental) | AstrBot `data/cmd_config.json` | Updates the model of an **existing** provider entry (`provider_id`): the top-level `model` field for AstrBot ≥ 4.10 (`provider_sources` layout), `model_config.model` for older versions. Never creates providers or touches keys or provider sources. |

Example `dsh` result:

```yaml
- id: agent-default-model
  config: {provider: openrouter, model: 'vendor/some-model:free'}
```

### Known limitations

- **AstrBot:** both layouts were checked against AstrBot source (v4.29.1); an entry matching
  neither raises an error instead of being skipped. AstrBot keeps its config in memory and rewrites
  the file when you save in the WebUI, so **restart AstrBot after a sync** (and avoid editing in
  the WebUI at the same time). Provider entries have no fallback list, so only the primary model is
  written; mapping fallbacks to AstrBot's `fallback_provider_ids` is not implemented yet.
- **YAML comments (0.3.0+):** install the optional extra (`pipx install "freemodel-sync[yaml-comments]"`) and
  `openai-yaml` edits the file with ruamel.yaml, keeping comments, key order and quoting. Without it,
  PyYAML is used and comments are dropped *when a value changes* (an unchanged file is never
  rewritten). Target option `preserve_comments: auto|true|false` (default `auto`). The `dsh` adapter
  always preserves comments.
- **Time-based pricing:** a `:free` model whose `pricing.overrides` has a non-zero price (for
  example at peak hours or for long contexts) is skipped with a warning.
- **Free quota:** the daily budget comes from `free_model_daily_requests` (never inferred from
  `is_free_tier`); `testing.daily_free_limit` overrides it, counted per UTC day.
  The counters are read once, before probing, and OpenRouter's `used` count can trail requests
  that were already sent, so shown quota figures may lag. When this tool's own probe count for the
  UTC day is higher than the reported `used`, the budget uses the local count.
- **Providers:** OpenRouter and Groq. SiliconFlow was evaluated but its API does not say which
  models are free; see [docs/providers.md](https://github.com/ndwlbj/freemodel-sync/blob/main/docs/providers.md).

## Notifications

- **Telegram:** set `notify.telegram` and export `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
- **Webhook** (e.g. a QQ bot bridge): set `notify.webhook.url_env` (default `FREEMODEL_SYNC_WEBHOOK_URL`).
  Webhook URLs usually contain a token, so keep them in the environment: an inline `notify.webhook.url`
  works but logs a warning, plus another if the config file is readable by other users.
  The POST body is `{"event": "primary_changed", "old", "new", "fallbacks", "text"}`.

Notification failures are logged (without tokens or full URLs) and never fail a sync.

## Daily free-model snapshot

An automated daily health check ([`daily-snapshot.yml`](https://github.com/ndwlbj/freemodel-sync/blob/main/.github/workflows/daily-snapshot.yml), about 09:17 Asia/Shanghai / 01:17 UTC)
discovers the free models, probes at most 15 of them per provider with one tiny request each
(within the account's free-request quota), and publishes the result to the `data` branch:
**[latest snapshot](https://github.com/ndwlbj/freemodel-sync/blob/data/snapshots/latest.md)**, with every day kept as `snapshots/YYYY-MM-DD.json`. The table shows
each model's status (`ok`, `403`, `404`, `429`, `timeout`, ...), latency and context length, plus the
changes since the previous day and models expiring soon. It is informational only: results come from
GitHub Actions at one moment and can differ for you, so run `freemodel-sync test` with your own key
before relying on a model.

## Writing a provider

Providers are plugins. Subclass `Provider`, implement `discover()` and `test()` (and optionally
`quota()`), and register it:

```python
from freemodel_sync.providers import Provider, register_provider

@register_provider
class MyProvider(Provider):
    name = "myprovider"
    base_url = "https://api.example.com/v1"
    api_key_env = "MYPROVIDER_API_KEY"

    def discover(self): ...
    def test(self, model, timeout=30.0): ...
```

Possible future providers (not implemented, no timeline): Zhipu GLM Flash, Google Gemini. Adapters follow the same pattern
(`freemodel_sync.adapters.base.Adapter` + `register_adapter`).

## Development

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest
```

Tests never touch the network (HTTP is mocked with `httpx.MockTransport`). See
[CONTRIBUTING.md](https://github.com/ndwlbj/freemodel-sync/blob/main/CONTRIBUTING.md).

## Security

To report a vulnerability privately, see [SECURITY.md](https://github.com/ndwlbj/freemodel-sync/blob/main/SECURITY.md).

- Keys are read only from environment variables; freemodel-sync does not write them to config files
  or print them.
  Log output (including `-v`) redacts Telegram bot tokens, Bearer tokens and `sk-` style keys, and
  HTTP request logging (`--debug-http`) is off by default.
- Symlinked targets are followed: the real file is backed up and replaced, the link is kept.
- Never commit your `config.yml`, `.env` files, backups or cache; the `.gitignore` covers the defaults.

## License

[MIT](https://github.com/ndwlbj/freemodel-sync/blob/main/LICENSE) © freemodel-sync contributors
