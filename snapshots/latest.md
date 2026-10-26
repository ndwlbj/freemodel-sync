# Free-model snapshot 2026-10-26

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.2, generated 2026-10-26T06:11:39Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 16 | 15 | daily free limit 50; 6 used / 44 left before this run, about 29 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**20** free models, **13** ok, 6 failed, 1 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 117 | 242 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 135 | 231 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 137 | 385 | 256000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 188 | 192 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 197 | 328 | 256000 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 223 | 742 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 239 | 249 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 277 | 390 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 305 | 330 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 395 | 408 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 805 | 1275 | 512000 | yes | 2026-12-31 |
| openrouter | `poolside/laguna-s-2.1:free` | ok | 1836 | 2257 | 262144 | yes | 2026-10-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 4017 | 5631 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 144 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 158 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 60 | 65536 | yes | - |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` | 404 | - | 100 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 188 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 21 | 1048576 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | not_probed | - | - | 262144 | yes | 2026-10-31 |

## Changes

Compared with 2026-10-25:

- Added: none
- Removed: none
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` ok -> 429, `openrouter|poolside/laguna-s-2.1:free` 429 -> ok, `openrouter|xingchen-agi/xing4.0-29b-a4b:free` 429 -> ok

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (5 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (5 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
