# Free-model snapshot 2026-11-18

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-18T08:32:11Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **16** ok, 2 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-120b` | ok | 95 | 121 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 155 | 171 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 170 | 263 | 1000000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 189 | 320 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 195 | 450 | 256000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 203 | 250 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 219 | 312 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 254 | 264 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 410 | 818 | 1000000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | ok | 439 | 709 | 1048576 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 467 | 475 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 498 | 1109 | 512000 | yes | 2026-12-31 |
| openrouter | `recursive/flint-v1.0:free` | ok | 781 | 1167 | 262144 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1128 | 1298 | 1024000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 1556 | 2821 | 1048576 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | ok | 2260 | 2268 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 121 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 21 | 1048576 | yes | 2026-11-19 |

## Changes

Compared with 2026-11-17:

- Added: none
- Removed: none
- Status changed: none

### Expiring within 14 days

- `openrouter|thinkingmachines/inkling-2-small:free`: 2026-11-19 (1 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
