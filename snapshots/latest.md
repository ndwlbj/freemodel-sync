# Free-model snapshot 2026-11-26

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-26T09:30:21Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 11 | 11 | daily free limit 50; 0 used / 50 left before this run, about 39 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**15** free models, **12** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 48 | 56 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 116 | 129 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 125 | 159 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 126 | 251 | 256000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | ok | 235 | 403 | 1048576 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 243 | 324 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 251 | 261 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 262 | 332 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 306 | 736 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 375 | 456 | 1000000 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 2236 | 2289 | 1024000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 13765 | 13878 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 112 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 110 | 262144 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | 429 | - | 286 | 1048576 | yes | - |

## Changes

Compared with 2026-11-25:

- Added: none
- Removed: none
- Status changed: `openrouter|baidu/ernie-5.5-flash-preview:free` 429 -> ok, `openrouter|particle-ai/particle-1:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
