# Free-model snapshot 2026-11-12

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-12T08:18:55Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **14** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 144 | 184 | 65536 | yes | 2026-11-13 |
| groq | `openai/gpt-oss-120b` | ok | 151 | 178 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 160 | 238 | 256000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 229 | 299 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 258 | 377 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 275 | 678 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 279 | 290 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 377 | 418 | 1000000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 398 | 405 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 441 | 972 | 512000 | yes | 2026-12-31 |
| groq | `openai/gpt-oss-20b` | ok | 605 | 620 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 640 | 700 | 1000000 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 753 | 762 | 1024000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 1082 | 1286 | 262144 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 102 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 141 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 28 | 1048576 | yes | - |

## Changes

Compared with 2026-11-11:

- Added: none
- Removed: none
- Status changed: none

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (1 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
