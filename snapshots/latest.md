# Free-model snapshot 2026-11-14

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-14T07:36:08Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 14 | 14 | daily free limit 50; 0 used / 50 left before this run, about 36 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**18** free models, **14** ok, 4 failed, 0 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 47 | 49 | 131072 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 152 | 165 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | ok | 200 | 332 | 256000 | yes | - |
| groq | `openai/gpt-oss-120b` | ok | 209 | 236 | 131072 | no | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | ok | 224 | 333 | 1000000 | yes | - |
| groq | `allam-2-7b` | ok | 242 | 252 | 4096 | no | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | ok | 244 | 337 | 1000000 | yes | - |
| openrouter | `cohere/north-mini-code:free` | ok | 273 | 371 | 256000 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | ok | 302 | 377 | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | 566 | 711 | 1000000 | yes | - |
| openrouter | `dots-studio/dots-3-note-preview:free` | ok | 788 | 1632 | 512000 | yes | 2026-12-31 |
| openrouter | `particle-ai/particle-1:free` | ok | 877 | 1457 | 1048576 | yes | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | ok | 938 | 947 | 1024000 | yes | - |
| openrouter | `inclusionai/ling-3.2-flash:free` | ok | 993 | 1627 | 1048576 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | 429 | - | 136 | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | 429 | - | 141 | 262144 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | error | - | 60413 | 262144 | yes | - |
| openrouter | `thinkingmachines/inkling-2-small:free` | 403 | - | 33 | 1048576 | yes | - |

## Changes

Compared with 2026-11-13:

- Added: `openrouter|inclusionai/ling-3.2-flash:free`
- Removed: `openrouter|apodex/apodex-1.1-mini:free`, `openrouter|liquid/lfm-2.5-2.6b:free`
- Status changed: `openrouter|recursive/flint-v1.0:free` ok -> error

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
