# Free-model snapshot 2026-10-30

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-10-30T07:05:04Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 15 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**19** free models, **12** ok, 7 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 67 | 67 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 193 | 325 | 256000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 216 | 306 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 220 | 782 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 235 | 262 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 251 | 357 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 293 | 302 | 4096 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 320 | 334 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 396 | 979 | 512000 | yes | 2026-12-31 |
| openrouter | `poolside/laguna-s-2.1:free` | ok | 513 | 572 | 262144 | yes | 2026-10-31 |
| openrouter | `google/gemma-4-31b-it:free` | ok | 662 | 684 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 2826 | 2944 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 129 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 106 | 65536 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | 429 | - | 96 | 262144 | yes | 2026-10-31 |
| openrouter | `recursive/flint-v1.0:free` | 503 | - | 260 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 19 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 54 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 636 | 262144 | yes | - |

## Changes

Compared with 2026-10-29:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` ok -> 429, `openrouter|google/gemma-4-31b-it:free` 429 -> ok, `openrouter|liquid/lfm-2.5-2.6b:free` ok -> 429, `openrouter|recursive/flint-v1.0:free` ok -> 503

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (1 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (1 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
