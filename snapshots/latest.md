# Free-model snapshot 2026-11-09

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-09T07:57:13Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **14** ok, 2 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-20b` | ok | 77 | 91 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 113 | 329 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 116 | 224 | 256000 | yes | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 125 | 154 | 65536 | yes | 2026-11-13 |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 162 | 240 | 262144 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 169 | 177 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 200 | 243 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 241 | 251 | 4096 | no | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 282 | 403 | 262144 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 333 | 348 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 349 | 428 | 1000000 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | ok | 387 | 618 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 1050 | 1862 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 7565 | 8087 | 512000 | yes | 2026-12-31 |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 156 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 191 | 262144 | yes | - |

## Changes

Compared with 2026-11-08:

- Added: none
- Removed: none
- Status changed: none

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (4 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
