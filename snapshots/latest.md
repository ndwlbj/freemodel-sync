# Free-model snapshot 2026-10-25

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.2, generated 2026-10-25T06:06:27Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 16 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**20** free models, **12** ok, 7 failed, 1 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 78 | 79 | 131072 | no | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 167 | 210 | 65536 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 178 | 191 | 131072 | no | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 192 | 628 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 204 | 421 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 243 | 270 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 262 | 799 | 256000 | yes | - |
| groq | `allam-2-7b` | ok | 267 | 277 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 278 | 375 | 1000000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 320 | 686 | 256000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 429 | 862 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 596 | 1036 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 116 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 135 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` | 404 | - | 102 | 262144 | yes | - |
| openrouter | `poolside/laguna-s-2.1:free` | 429 | - | 114 | 262144 | yes | 2026-10-31 |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 32 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 57 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 227 | 262144 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | not_probed | - | - | 262144 | yes | 2026-10-31 |

## Changes

Compared with 2026-10-24:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` ok -> 429, `openrouter|nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` error -> ok, `openrouter|poolside/laguna-s-2.1:free` ok -> 429, `openrouter|xingchen-agi/xing4.0-29b-a4b:free` ok -> 429

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (6 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (6 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
