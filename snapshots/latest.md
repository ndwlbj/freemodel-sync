# Free-model snapshot 2026-11-04

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-04T07:29:20Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **12** ok, 5 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 107 | 108 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 127 | 247 | 1000000 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 155 | 182 | 65536 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 199 | 213 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 250 | 365 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 269 | 296 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 331 | 340 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 348 | 503 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 470 | 637 | 262144 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 494 | 1002 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 553 | 997 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 1264 | 2720 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 104 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 106 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 60 | 1048576 | yes | 2026-11-04 |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 38 | 1048576 | yes | 2026-11-04 |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 467 | 262144 | yes | - |

## Changes

Compared with 2026-11-03:

- Added: none
- Removed: none
- Status changed: `groq|qwen/qwen3.8-27b` timeout -> ok, `openrouter|recursive/flint-v1.0:free` 503 -> ok

### Expiring within 14 days

- `openrouter|thinkingmachines/inkling-small:free`: 2026-11-04 (0 days)
- `openrouter|thinkingmachines/inkling:free`: 2026-11-04 (0 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
