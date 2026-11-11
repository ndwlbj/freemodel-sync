# Free-model snapshot 2026-11-11

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-11T07:44:27Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 13 | 13 | daily free limit 50; 0 used / 50 left before this run, about 37 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**17** free models, **14** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `openai/gpt-oss-120b` | ok | 113 | 138 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 127 | 262 | 256000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 154 | 234 | 256000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 200 | 214 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 215 | 304 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 223 | 232 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 301 | 380 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 421 | 950 | 512000 | yes | 2026-12-31 |
| openrouter | `recursive/flint-v1.0:free` | ok | 424 | 526 | 262144 | yes | - |
| groq | `qwen/qwen3.8-27b` | ok | 505 | 507 | 131072 | no | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 633 | 711 | 65536 | yes | 2026-11-13 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 957 | 1159 | 1000000 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1023 | 1086 | 1024000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 2609 | 2792 | 262144 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 64 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 92 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 21 | 1048576 | yes | - |

## Changes

Compared with 2026-11-10:

- Added: `openrouter|baidu/ernie-5.5-flash-preview:free`
- Removed: `openrouter|xingchen-agi/xing4.0-29b-a4b:free`
- Status changed: none

### Expiring within 14 days

- `openrouter|liquid/lfm-2.5-2.6b:free`: 2026-11-13 (2 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
