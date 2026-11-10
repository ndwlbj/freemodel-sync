# Free-model snapshot 2026-11-10

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-10T08:25:04Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **13** ok, 4 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 88 | 222 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 100 | 196 | 256000 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 101 | 131 | 65536 | yes | 2026-11-13 |
| groq | `qwen/qwen3.8-27b` | ok | 110 | 118 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 153 | 235 | 256000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 158 | 269 | 262144 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 205 | 231 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 238 | 248 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 785 | 1465 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 872 | 999 | 512000 | yes | 2026-12-31 |
| groq | `openai/gpt-oss-20b` | ok | 897 | 910 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 2169 | 9731 | 1000000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 5086 | 5906 | 262144 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 133 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 159 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 309 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 804 | 262144 | yes | - |

## Changes

Compared with 2026-11-09:

- Added: `openrouter|thinkingmachines/inkling-2-small:free`
- Removed: none
- Status changed: `openrouter|xingchen-agi/xing4.0-29b-a4b:free` ok -> 429

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (3 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
