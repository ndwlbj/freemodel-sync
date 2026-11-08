# Free-model snapshot 2026-11-08

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-08T07:17:24Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **14** ok, 2 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 126 | 236 | 1000000 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 147 | 185 | 65536 | yes | 2026-11-13 |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 195 | 280 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 206 | 371 | 131072 | no | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 245 | 351 | 262144 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 301 | 368 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 325 | 443 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 425 | 543 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 457 | 458 | 4096 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 517 | 518 | 131072 | no | - |
| groq | `qwen/qwen3.8-27b` | ok | 684 | 686 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 839 | 1262 | 512000 | yes | 2026-12-31 |
| openrouter | `recursive/flint-v1.0:free` | ok | 1275 | 1454 | 262144 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 3746 | 4207 | 262144 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 277 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 89 | 262144 | yes | - |

## Changes

Compared with 2026-11-07:

- Added: none
- Removed: none
- Status changed: `openrouter|xingchen-agi/xing4.0-29b-a4b:free` 429 -> ok

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (5 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
