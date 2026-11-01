# Free-model snapshot 2026-11-01

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-11-01T07:30:27Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **11** ok, 6 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-20b` | ok | 103 | 116 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 106 | 133 | 131072 | no | - |
| groq | `qwen/qwen3.8-27b` | ok | 126 | 127 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 165 | 279 | 256000 | yes | - |
| groq | `allam-2-7b` | ok | 219 | 227 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 310 | 382 | 1000000 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 362 | 487 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 371 | 400 | 256000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 423 | 783 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 550 | 642 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 6798 | 52109 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 83 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 137 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 61 | 65536 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | 503 | - | 101 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 19 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 25 | 1048576 | yes | - |

## Changes

Compared with 2026-10-31:

- Added: none
- Removed: `openrouter|poolside/laguna-s-2.1:free`, `openrouter|poolside/laguna-xs-2.1:free`
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` ok -> 429, `openrouter|xingchen-agi/xing4.0-29b-a4b:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
