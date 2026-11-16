# Free-model snapshot 2026-11-16

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-16T07:58:09Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **14** ok, 4 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-120b` | ok | 40 | 66 | 131072 | no | - |
| groq | `qwen/qwen3.8-27b` | ok | 116 | 123 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 117 | 192 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 123 | 328 | 256000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 166 | 186 | 131072 | no | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 193 | 298 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 216 | 224 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 315 | 415 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 407 | 2437 | 1000000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 446 | 520 | 256000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | ok | 477 | 492 | 1048576 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 708 | 822 | 262144 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1424 | 1522 | 1024000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 7019 | 7271 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 85 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 73 | 262144 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | 429 | - | 980 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 19 | 1048576 | yes | - |

## Changes

Compared with 2026-11-15:

- Added: none
- Removed: none
- Status changed: `openrouter|inclusionai/ling-3.2-flash:free` ok -> 429, `openrouter|liquid/lfm-3-1.7b:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
