# Free-model snapshot 2026-11-07

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-07T07:08:10Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **13** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 91 | 191 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 95 | 216 | 1000000 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 115 | 132 | 65536 | yes | 2026-11-13 |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 120 | 183 | 262144 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 129 | 143 | 131072 | no | - |
| groq | `qwen/qwen3.8-27b` | ok | 136 | 138 | 131072 | no | - |
| openrouter | `cohere/north-mini-code:free` | ok | 143 | 237 | 256000 | yes | - |
| groq | `allam-2-7b` | ok | 238 | 248 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 385 | 509 | 1000000 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 420 | 530 | 262144 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 460 | 485 | 131072 | no | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 480 | 933 | 512000 | yes | 2026-12-31 |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 2992 | 3362 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 157 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 148 | 262144 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 668 | 262144 | yes | - |

## Changes

Compared with 2026-11-06:

- Added: `openrouter|liquid/lfm-3-1.7b:free`
- Removed: none
- Status changed: `openrouter|liquid/lfm-2.5-2.6b:free` 429 -> ok, `openrouter|xingchen-agi/xing4.0-29b-a4b:free` ok -> 429

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (6 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
