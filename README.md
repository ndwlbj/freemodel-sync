# freemodel-sync

[![CI](https://github.com/ghwghw19/freemodel-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/ghwghw19/freemodel-sync/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

[English](README.md) | [简体中文](README.zh-CN.md)

**Discover, test and rank free LLMs — then write the best one (plus fallbacks) into the configs of tools you already use.**

Free LLM endpoints come and go: models get added, rate-limited, deprecated or quietly start
costing money. `freemodel-sync` keeps your bots and scripts pointed at a free model that
actually works today.

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
3. **Probe** each candidate with one tiny streaming request (`max_tokens: 8`) using *your own*
   OpenRouter key, measuring availability and time-to-first-token. Probing is frugal:
   candidates are tried in order of promise, results are cached (6 h by default), at most
   `max_tests` new probes are made per run, and the round stops while keeping
   `reserve_requests` of the free requests left today, as reported by
   `free_model_daily_requests.remaining` in `GET /api/v1/key` (UTC day; 50/day below 10
   purchased credits, 1000/day above). If the key endpoint reports nothing, a conservative
   50/day is assumed against a local UTC-day counter.
   - **Account problems are not model failures.** A 401/402/403 or an OpenRouter platform 429
     (free-model per-minute/per-day cap) stops the round after that single request; the model is
     *not* cached as failed, and `Retry-After` / `X-RateLimit-Reset` pause later runs until the
     reset. Upstream-provider 429s, 5xx and timeouts count as transient failures and are retried
     after `transient_ttl_minutes` (30 by default).
   - Without an API key, `test`, `rank` and `sync` exit with an error and send nothing.
4. **Rank** with an explainable score (availability ≫ latency, context, tools, expiry).
5. **Write** the primary model and fallback list into each configured target. Every write is
   idempotent (unchanged → untouched), supports `--dry-run` with a diff, makes a timestamped
   `*.bak-*` backup and replaces the file atomically. If no model passes its probe, **nothing is written**.
6. **Notify** (optional) via Telegram or a generic webhook when the primary model changes.

## Install

```bash
pipx install git+https://github.com/ghwghw19/freemodel-sync
# or run without installing
uvx --from git+https://github.com/ghwghw19/freemodel-sync freemodel-sync --help
# from a local checkout
pipx install .
```

Requires Python 3.9+. Runtime dependencies: `httpx`, `PyYAML`.

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
or missing credits (no file written, no model marked as failed).

`sync --dry-run` is zero-cost: it uses only cached probe results (from an earlier `test`/`sync`), sends no chat or `/key` request, needs no API key, and writes no target, state or cache file. It still fetches the public model list. Add `--probe` to probe as usual during a dry run (this spends free-tier requests and updates the cache). `rank --no-probe` and `sync --no-probe` likewise use cached results only.

## Configuration

Default location: `~/.config/freemodel-sync/config.yml` (override with `-c FILE` or
`$FREEMODEL_SYNC_CONFIG`). Every key is optional; see
[`examples/config.example.yml`](examples/config.example.yml) for the full annotated file.

## Targets (adapters)

| adapter | file | what it writes |
| --- | --- | --- |
| `openai-env` | `KEY=VALUE` env file | `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_FALLBACK_MODELS` (names configurable). Other lines, comments and your API key are left untouched. |
| `openai-yaml` | any YAML file | `base_url`, `model`, `fallback_models` under a dotted `key_path` (default `llm`). |
| `dsh` | dsh (DeepSeek Harness) `cordis.patch.yml`-style list | Replaces only the `agent-default-model` entry with `config: {provider: <p>, model: '<m>'}`; other entries and comments are kept byte-for-byte. Use `provider_map` to map `openrouter` to your dsh provider id. Optional `fallback_entry_id` writes the fallback list as a separate entry. |
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
- **YAML comments:** `openai-yaml` uses PyYAML, which drops comments *when a value changes*
  (an unchanged file is never rewritten). The `dsh` adapter preserves comments.
- **Free quota:** the daily budget comes from `free_model_daily_requests` (never inferred from
  `is_free_tier`); `testing.daily_free_limit` overrides it, counted per UTC day.
- Only OpenRouter is implemented in this release (see below).

## Notifications

- **Telegram:** set `notify.telegram` and export `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
- **Webhook** (e.g. a QQ bot bridge): set `notify.webhook.url_env` (default `FREEMODEL_SYNC_WEBHOOK_URL`).
  The POST body is `{"event": "primary_changed", "old", "new", "fallbacks", "text"}`.

Notification failures are logged (without tokens or full URLs) and never fail a sync.

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

Planned: SiliconFlow, Zhipu GLM Flash, Groq, Google Gemini. Adapters follow the same pattern
(`freemodel_sync.adapters.base.Adapter` + `register_adapter`).

## Development

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest
```

Tests never touch the network (HTTP is mocked with `httpx.MockTransport`).

## Security

- Keys are read only from environment variables and are never written to config files or printed.
  Log output (including `-v`) redacts Telegram bot tokens, Bearer tokens and `sk-` style keys, and
  HTTP request logging (`--debug-http`) is off by default.
- Symlinked targets are followed: the real file is backed up and replaced, the link is kept.
- Never commit your `config.yml`, `.env` files, backups or cache; the `.gitignore` covers the defaults.

## License

[MIT](LICENSE) © freemodel-sync contributors
