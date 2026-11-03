# Free-model snapshot 2026-11-03

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-03T07:55:03Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **10** ok, 7 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 143 | 332 | 65536 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 157 | 216 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 181 | 309 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 231 | 244 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 268 | 278 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 306 | 433 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 310 | 428 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 374 | 399 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 490 | 1285 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 1354 | 1894 | 512000 | yes | 2026-12-31 |
| groq | `qwen/qwen3.8-27b` | timeout | - | 30021 | 131072 | no | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 74 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 91 | 262144 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | 503 | - | 120 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 23 | 1048576 | yes | 2026-11-04 |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 31 | 1048576 | yes | 2026-11-04 |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 1221 | 262144 | yes | - |

## Changes

Compared with 2026-11-02:

- Added: none
- Removed: none
- Status changed: `groq|qwen/qwen3.8-27b` ok -> timeout

### Expiring within 14 days

- `openrouter|thinkingmachines/inkling-small:free`: 2026-11-04 (1 days)
- `openrouter|thinkingmachines/inkling:free`: 2026-11-04 (1 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
