# Free-model snapshot 2026-10-28

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-10-28T06:51:16Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 15 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**19** free models, **10** ok, 9 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 111 | 114 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 150 | 275 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 171 | 185 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 172 | 300 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 209 | 667 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 281 | 307 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 289 | 300 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 325 | 435 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 490 | 610 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 1575 | 2062 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 83 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 83 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 129 | 65536 | yes | - |
| openrouter | `poolside/laguna-s-2.1:free` | 429 | - | 85 | 262144 | yes | 2026-10-31 |
| openrouter | `poolside/laguna-xs-2.1:free` | 429 | - | 77 | 262144 | yes | 2026-10-31 |
| openrouter | `recursive/flint-v1.0:free` | 429 | - | 201 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 35 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 40 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 1782 | 262144 | yes | - |

## Changes

Compared with 2026-10-27:

- Added: none
- Removed: `openrouter|nvidia/nemotron-3-super-120b-a12b:free`
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` ok -> 429, `openrouter|xingchen-agi/xing4.0-29b-a4b:free` ok -> 429

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (3 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (3 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
