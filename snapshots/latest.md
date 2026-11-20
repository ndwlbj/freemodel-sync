# Free-model snapshot 2026-11-20

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-20T08:31:59Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **11** ok, 5 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 54 | 56 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 153 | 166 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 161 | 259 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 216 | 243 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 243 | 253 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 268 | 364 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 299 | 312 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 369 | 666 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 435 | 1159 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | ok | 597 | 603 | 262144 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 6553 | 7677 | 512000 | yes | 2026-12-31 |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | 429 | - | 402 | 1024000 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 286 | 262144 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | 429 | - | 873 | 1048576 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | error | - | 24240 | 262144 | yes | - |
| openrouter | `particle-ai/particle-1:free` | 429 | - | 321 | 1048576 | yes | - |

## Changes

Compared with 2026-11-19:

- Added: none
- Removed: `openrouter|cohere/north-mini-code:free`, `openrouter|thinkingmachines/inkling-2-small:free`
- Status changed: `openrouter|baidu/ernie-5.5-flash-preview:free` ok -> 429, `openrouter|google/gemma-4-26b-a4b-it:free` 429 -> ok, `openrouter|inclusionai/ling-3.2-flash:free` ok -> 429, `openrouter|liquid/lfm-3-1.7b:free` ok -> error, `openrouter|particle-ai/particle-1:free` ok -> 429

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
