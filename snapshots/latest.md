# Free-model snapshot 2026-11-24

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-24T10:54:26Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **15** ok, 1 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 52 | 53 | 131072 | no | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 159 | 235 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 177 | 357 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 196 | 252 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 212 | 227 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 238 | 262 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 247 | 256 | 4096 | no | - |
| openrouter | `particle-ai/particle-1:free` | ok | 439 | 450 | 1048576 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 452 | 965 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 453 | 575 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 486 | 949 | 262144 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 737 | 856 | 1024000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 820 | 920 | 1048576 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | ok | 1337 | 1346 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 7281 | 7444 | 1000000 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 164 | 262144 | yes | - |

## Changes

Compared with 2026-11-23:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` 429 -> ok, `openrouter|inclusionai/ling-3.2-flash:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
