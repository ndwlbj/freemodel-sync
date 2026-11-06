# Free-model snapshot 2026-11-06

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-06T07:55:04Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 11 | 11 | daily free limit 50; 0 used / 50 left before this run, about 39 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**15** free models, **12** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 139 | 477 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 146 | 274 | 256000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 188 | 192 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 197 | 286 | 256000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 227 | 241 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 235 | 261 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 248 | 258 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 398 | 517 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 489 | 583 | 1000000 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 570 | 1027 | 262144 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 707 | 829 | 262144 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 1071 | 1768 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 106 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 117 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 158 | 65536 | yes | - |

## Changes

Compared with 2026-11-05:

- Added: none
- Removed: none
- Status changed: `openrouter|xingchen-agi/xing4.0-29b-a4b:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
