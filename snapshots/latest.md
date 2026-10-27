# Free-model snapshot 2026-10-27

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-10-27T06:15:42Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 16 | 15 | daily free limit 50; 7 used / 43 left before this run, about 28 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**20** free models, **12** ok, 7 failed, 1 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 61 | 63 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 180 | 193 | 131072 | no | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 208 | 254 | 65536 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 233 | 1259 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 254 | 452 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 255 | 415 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 261 | 287 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 302 | 477 | 256000 | yes | - |
| groq | `allam-2-7b` | ok | 316 | 326 | 4096 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 482 | 985 | 512000 | yes | 2026-12-31 |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 510 | 698 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 701 | 798 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 120 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 114 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` | 404 | - | 147 | 262144 | yes | - |
| openrouter | `poolside/laguna-s-2.1:free` | 429 | - | 132 | 262144 | yes | 2026-10-31 |
| openrouter | `recursive/flint-v1.0:free` | 429 | - | 191 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 25 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 39 | 1048576 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | not_probed | - | - | 262144 | yes | 2026-10-31 |

## Changes

Compared with 2026-10-26:

- Added: none
- Removed: none
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` 429 -> ok, `openrouter|poolside/laguna-s-2.1:free` ok -> 429, `openrouter|recursive/flint-v1.0:free` ok -> 429

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (4 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (4 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
