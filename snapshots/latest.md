# Free-model snapshot 2026-11-23

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-23T09:00:21Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 12 | 12 | daily free limit 50; 0 used / 50 left before this run, about 38 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**16** free models, **13** ok, 3 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 51 | 59 | 131072 | no | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 147 | 759 | 262144 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 152 | 166 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 181 | 307 | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 190 | 271 | 1000000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 220 | 246 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 274 | 372 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 309 | 319 | 4096 | no | - |
| openrouter | `particle-ai/particle-1:free` | ok | 352 | 398 | 1048576 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | ok | 441 | 683 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 528 | 586 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 617 | 905 | 512000 | yes | 2026-12-31 |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 1387 | 1397 | 1024000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 378 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 71 | 262144 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | 429 | - | 251 | 1048576 | yes | - |

## Changes

Compared with 2026-11-22:

- Added: `openrouter|dots-studio/dots-3-note-preview:free`
- Removed: none
- Status changed: `openrouter|baidu/ernie-5.5-flash-preview:free` 429 -> ok

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
