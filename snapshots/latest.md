# Free-model snapshot 2026-10-31

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.3.3, generated 2026-10-31T06:59:21Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 15 | 15 | daily free limit 50; 0 used / 50 left before this run, about 35 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**19** free models, **13** ok, 6 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 59 | 59 | 131072 | no | - |
| openrouter | `liquid/lfm-2.5-2.6b:free` | ok | 169 | 205 | 65536 | yes | - |
| openrouter | `poolside/laguna-xs-2.1:free` | ok | 172 | 287 | 262144 | yes | 2026-10-31 |
| openrouter | `cohere/north-mini-code:free` | ok | 179 | 260 | 256000 | yes | - |
| groq | `openai/gpt-oss-20b` | ok | 246 | 259 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 253 | 278 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 269 | 406 | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 304 | 581 | 256000 | yes | - |
| groq | `allam-2-7b` | ok | 323 | 333 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 339 | 604 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 471 | 970 | 512000 | yes | 2026-12-31 |
| openrouter | `poolside/laguna-s-2.1:free` | ok | 675 | 742 | 262144 | yes | 2026-10-31 |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 757 | 916 | 1000000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 102 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 97 | 262144 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | 503 | - | 290 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-small:free` | 403 | - | 42 | 1048576 | yes | - |
| openrouter | `thinkingmachines/inkling:free` | 403 | - | 25 | 1048576 | yes | - |
| openrouter | `xingchen-agi/xing4.0-29b-a4b:free` | 429 | - | 396 | 262144 | yes | - |

## Changes

Compared with 2026-10-30:

- Added: none
- Removed: none
- Status changed: `openrouter|google/gemma-4-31b-it:free` ok -> 429, `openrouter|liquid/lfm-2.5-2.6b:free` 429 -> ok, `openrouter|poolside/laguna-xs-2.1:free` 429 -> ok

### Expiring within 14 days

- `openrouter|poolside/laguna-s-2.1:free`: 2026-10-31 (0 days)
- `openrouter|poolside/laguna-xs-2.1:free`: 2026-10-31 (0 days)

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
