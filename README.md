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
   `max_tests` new probes are made per run, and a daily counter keeps a reserve below the
   free-tier limit reported by `GET /api/v1/key` (50 requests/day, or 1000 after buying ≥10 credits).
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

Run `sync` from cron or a systemd timer, e.g. every 3 hours:

```cron
0 */3 * * * OPENROUTER_API_KEY=... freemodel-sync sync >> ~/.cache/freemodel-sync/sync.log 2>&1
```

Exit codes: `0` success, `1` error (bad config, a target failed), `2` no usable model (no file written).

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
| `astrbot` (experimental) | AstrBot `data/cmd_config.json` | Updates `model_config.model` of an **existing** provider entry (`provider_id`). Never creates providers or touches keys. |

Example `dsh` result:

```yaml
- id: agent-default-model
  config: {provider: openrouter, model: 'vendor/some-model:free'}
```

### Known limitations

- **AstrBot:** the adapter follows the documented `provider` list in `data/cmd_config.json`
  (`type: openai_chat_completion`, `model_config.model`). Newer AstrBot releases (v4.x) manage
  providers through the WebUI and may store them differently; please verify on your version and
  restart AstrBot after a change. AstrBot provider entries have no fallback list, so only the
  primary model is written.
- **YAML comments:** `openai-yaml` uses PyYAML, which drops comments *when a value changes*
  (an unchanged file is never rewritten). The `dsh` adapter preserves comments.
- **Free-tier detection:** OpenRouter's `is_free_tier` flag does not say whether ≥10 credits were
  bought; set `testing.daily_free_limit` if the heuristic is wrong for your account.
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

- Keys are read only from environment variables and are never written, logged or printed.
- Never commit your `config.yml`, `.env` files, backups or cache; the `.gitignore` covers the defaults.

## License

[MIT](LICENSE) © freemodel-sync contributors
