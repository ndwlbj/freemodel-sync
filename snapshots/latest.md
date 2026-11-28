# Free-model snapshot 2026-11-28

Automated daily health check by [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 0.4.0, generated 2026-11-28T08:54:39Z. Results are informational only: one tiny request per model from GitHub Actions, so availability and latency can differ for you.

## Providers

| Provider | Status | Free models | Probes sent | Notes |
|---|---|---|---|---|
| openrouter | ok | 10 | 0 | daily free-request budget reached (keeping 10 in reserve); daily free limit 50; 53 used / 0 left before this run, about 0 left after it (data may lag) |
| groq | ok | 4 | 4 | - |

**14** free models, **4** ok, 0 failed, 10 not probed (probe cap 15 per provider).

## Models

| Provider | Model | Status | TTFT ms | Total ms | Context | Tools | Expires |
|---|---|---|---|---|---|---|---|
| groq | `qwen/qwen3.8-27b` | ok | 81 | 88 | 131072 | no | - |
| groq | `openai/gpt-oss-120b` | ok | 141 | 164 | 131072 | no | - |
| groq | `allam-2-7b` | ok | 242 | 252 | 4096 | no | - |
| groq | `openai/gpt-oss-20b` | ok | 269 | 283 | 131072 | no | - |
| openrouter | `baidu/ernie-5.5-flash-preview:free` | not_probed | - | - | 1024000 | yes | - |
| openrouter | `google/gemma-4-26b-a4b-it:free` | not_probed | - | - | 262144 | yes | - |
| openrouter | `google/gemma-4-31b-it:free` | not_probed | - | - | 262144 | yes | - |
| openrouter | `liquid/lfm-3-1.7b:free` | not_probed | - | - | 262144 | yes | - |
| openrouter | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | not_probed | - | - | 256000 | yes | - |
| openrouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | not_probed | - | - | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-lightning:free` | not_probed | - | - | 1000000 | yes | - |
| openrouter | `nvidia/nemotron-3.5-super-vl:free` | not_probed | - | - | 1000000 | yes | - |
| openrouter | `particle-ai/particle-1:free` | not_probed | - | - | 1048576 | yes | - |
| openrouter | `recursive/flint-v1.0:free` | not_probed | - | - | 262144 | yes | - |

## Changes

Compared with 2026-11-27:

- Added: none
- Removed: `openrouter|inclusionai/ling-3.2-flash:free`
- Status changed: none

### Expiring within 14 days

None announced.

Expiry dates come from OpenRouter's `expiration_date` field. Groq publishes no expiry dates, so Groq models never appear here.
