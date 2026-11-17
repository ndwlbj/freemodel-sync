# Free-model snapshot 2026-11-17

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-17T09:12:16Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **16** ok, 2 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 99 | 239 | 256000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 109 | 117 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 131 | 226 | 1000000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 138 | 223 | 262144 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 187 | 405 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 239 | 249 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 252 | 313 | 1000000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | ok | 267 | 276 | 1048576 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 273 | 300 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 339 | 339 | 131072 | no | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | ok | 362 | 373 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 377 | 485 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 803 | 1560 | 512000 | yes | 2026-12-31 |
| openrouter | `cohere/north-mini-code:free` | ok | 987 | 1036 | 256000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 1296 | 1924 | 1048576 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1905 | 1923 | 1024000 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 63 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 13 | 1048576 | yes | - |

## Changes

Compared with 2026-11-16:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` 429 -> ok, `openrouter|inclusionai/ling-3.2-flash:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
