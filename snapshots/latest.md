# Free-model snapshot 2026-11-19

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-19T08:46:19Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **15** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 106 | 167 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 116 | 363 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 125 | 150 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 147 | 203 | 256000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 151 | 159 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 189 | 195 | 131072 | no | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 198 | 325 | 262144 | yes | - |
| groq | `allam-2-7b` | ok | 235 | 244 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 319 | 336 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 344 | 698 | 1000000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | ok | 372 | 383 | 1048576 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 599 | 653 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 792 | 1740 | 512000 | yes | 2026-12-31 |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1334 | 1342 | 1024000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 1576 | 2040 | 1048576 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 79 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 117 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 16 | 1048576 | yes | 2026-11-19 |

## Changes

Compared with 2026-11-18:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-26b-a4b-it:free` ok -> 429

### Expiring within 14 days

- `openrouter|thinkingmachines/inkling-2-small:free`: 2026-11-19 (0 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
