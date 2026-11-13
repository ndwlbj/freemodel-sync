# Free-model snapshot 2026-11-13

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-13T07:55:33Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 15 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**19** free models, **16** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 55 | 60 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 131 | 229 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 143 | 157 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 147 | 203 | 256000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 151 | 217 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 242 | 253 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 293 | 362 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 297 | 323 | 131072 | no | - |
| openrouter | `particle-ai/particle-1:free` | ok | 475 | 532 | 1048576 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 486 | 1154 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 492 | 580 | 1000000 | yes | - |
| openrouter | `apodex/apodex-1.1-mini:free` | ok | 517 | 589 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 712 | 774 | 65536 | yes | 2026-11-13 |
| openrouter | `recursive/flint-v1.0:free` | ok | 1322 | 1538 | 262144 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1355 | 1362 | 1024000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 30574 | 31050 | 256000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 154 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 173 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 22 | 1048576 | yes | - |

## Changes

Compared with 2026-11-12:

- Added: `openrouter|apodex/apodex-1.1-mini:free`, `openrouter|particle-ai/particle-1:free`
- Removed: none
- Status changed: none

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (0 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
