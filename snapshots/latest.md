# Free-model snapshot 2026-10-29

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-10-29T07:03:19Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 15 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**19** free models, **14** ok, 5 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 47 | 49 | 131072 | no | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 122 | 155 | 65536 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 138 | 152 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 160 | 542 | 256000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 191 | 279 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 191 | 455 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 199 | 226 | 131072 | no | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 211 | 615 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 253 | 261 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 444 | 552 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | ok | 580 | 618 | 262144 | yes | - |
| openrouter | `poolside/laguna-s-2.1:free` | ok | 610 | 644 | 262144 | yes | 2026-10-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 829 | 1255 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 2970 | 3578 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 182 | 262144 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | 429 | - | 686 | 262144 | yes | 2026-10-31 |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 38 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 38 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 1151 | 262144 | yes | - |

## Changes

Compared with 2026-10-28:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` 429 -> ok, `openrouter|liquid/lfm-2.5-2.6b:free` 429 -> ok, `openrouter|poolside/laguna-s-2.1:free` 429 -> ok, `openrouter|recursive/flint-v1.0:free` 429 -> ok

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (2 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (2 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
