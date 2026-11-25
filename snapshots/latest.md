# Free-model snapshot 2026-11-25

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-25T09:50:47Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 11 | 11 | daily free limit 50; 0 used / 50 left before this run, about 39 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**15** free models, **10** ok, 5 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 67 | 75 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 122 | 263 | 256000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 123 | 136 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 130 | 302 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 131 | 157 | 131072 | no | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 171 | 237 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 235 | 244 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 354 | 383 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 397 | 754 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 1405 | 2129 | 262144 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | 429 | - | 759 | 1024000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 75 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 100 | 262144 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | 429 | - | 340 | 1048576 | yes | - |
| openrouter | `particle-ai/particle-1:free` | 429 | - | 152 | 1048576 | yes | - |

## Changes

Compared with 2026-11-24:

- Added: none
- Removed: `openrouter|dots-studio/dots-3-note-preview:free`
- Status changed: `openrouter|baidu/ernie-5.5-flash-preview:free` ok -> 429, `openrouter|google/gemma-4-26b-a4b-it:free` ok -> 429, `openrouter|inclusionai/ling-3.2-flash:free` ok -> 429, `openrouter|particle-ai/particle-1:free` ok -> 429

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
