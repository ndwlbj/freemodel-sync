# Free-model snapshot 2026-11-15

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-15T07:49:59Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **14** ok, 4 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `cohere/north-mini-code:free` | ok | 135 | 210 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 161 | 187 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 190 | 256 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 266 | 276 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 314 | 436 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 316 | 329 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 494 | 973 | 512000 | yes | 2026-12-31 |
| openrouter | `particle-ai/particle-1:free` | ok | 584 | 593 | 1048576 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 654 | 756 | 262144 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 662 | 668 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 707 | 1123 | 1000000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 899 | 1481 | 1048576 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 2012 | 2347 | 256000 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 2146 | 2377 | 1024000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 87 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 125 | 262144 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | 429 | - | 82 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 31 | 1048576 | yes | - |

## Changes

Compared with 2026-11-14:

- Added: none
- Removed: none
- Status changed: `openrouter|liquid/lfm-3-1.7b:free` ok -> 429, `openrouter|recursive/flint-v1.0:free` error -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
