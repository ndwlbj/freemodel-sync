# Free-model snapshot 2026-11-05

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-05T07:55:00Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 11 | 11 | daily free limit 50; 0 used / 50 left before this run, about 39 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**15** free models, **11** ok, 4 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 93 | 194 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 96 | 184 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 130 | 155 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 170 | 298 | 256000 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 172 | 174 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 237 | 247 | 4096 | no | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 274 | 385 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 302 | 377 | 1000000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 328 | 340 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 417 | 598 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 479 | 1053 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 154 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 140 | 262144 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | 429 | - | 40 | 65536 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 2442 | 262144 | yes | - |

## Changes

Compared with 2026-11-04:

- Added: none
- Removed: `openrouter|thinkingmachines/inkling-small:free`, `openrouter|thinkingmachines/inkling:free`
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` ok -> 429

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
