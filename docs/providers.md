# Providers: how "free" is decided

freemodel-sync only selects models that cost nothing to use. Each provider
needs a rule for this that can be checked, ideally from its API. This page
records the rule, the endpoints and fields used, and the official sources.
Sources were checked on 2026-10-22.

## OpenRouter (`openrouter`, default)

- Model list: `GET https://openrouter.ai/api/v1/models`, public, no key needed.
- A model is free when its id ends in `:free`, `pricing.prompt` and
  `pricing.completion` are `0`, every entry in `pricing.overrides` (prices by
  time of day or context length) is `0` too, and it takes and returns text.
- Quota: `GET /api/v1/key`, field `free_model_daily_requests`
  (`used` / `limit` / `remaining`, per UTC day).
- Errors: 401/402/403 and OpenRouter platform 429s are account problems.
  Upstream-provider 429s (with `error.metadata.provider_name`), 408 and 5xx are
  transient.
- Sources: <https://openrouter.ai/docs/api/api-reference/models/get-models>,
  <https://openrouter.ai/docs/api-reference/limits>.

## Groq (`groq`)

Available since freemodel-sync 0.3.0 (multi-provider ranking was added in the same release).

Groq's model list has no prices, so freeness is decided by the **account
plan**, not per model:

- On Groq's **Free plan** an organization has no payment method and cannot be
  billed; every model is usable within per-model rate limits. Upgrading to the
  Developer plan requires a payment method, after which usage is billed.
- The API does not say which plan an organization is on. freemodel-sync
  therefore lists or probes nothing until you confirm with
  `providers.groq.plan: free`. If you upgrade, remove the line or disable Groq.

Endpoints and fields:

- Model list: `GET https://api.groq.com/openai/v1/models` (needs the key).
  Fields used: `id`, `active` (inactive models are dropped) and
  `context_window`. Tool support is not reported, so it is treated as unknown.
  Speech, TTS and guard models (`whisper-*`, `*orpheus*`, `*prompt-guard*`,
  `*safeguard*`) are dropped by `filters.exclude_non_chat`.
- Probe: `POST /openai/v1/chat/completions` streaming, with
  `max_completion_tokens` (Groq's name for the completion budget).
- Quota: there is no quota endpoint. `x-ratelimit-remaining-requests` and
  `x-ratelimit-reset-requests` refer to requests per day (RPD); probing
  stops when the remaining count reaches `testing.reserve_requests` and later
  runs wait for the reset. `retry-after` is honoured.
- Errors: 401/403 are account problems. 429 is treated as an account problem
  too, conservatively: Groq probing stops for that run and resumes after
  `retry-after`. 498 (flex capacity), 408 and 5xx are transient; other 4xx
  count as a model failure.
- Sources: <https://console.groq.com/docs/models>,
  <https://console.groq.com/docs/api-reference#models-list>,
  <https://console.groq.com/docs/rate-limits>,
  <https://console.groq.com/docs/errors>,
  <https://console.groq.com/docs/billing-faqs>.

## Considered and not implemented: SiliconFlow

SiliconFlow is OpenAI-compatible and has free models, but its API cannot tell
which ones are free:

- `GET https://api.siliconflow.cn/v1/models` (also `api.siliconflow.com`)
  returns only `id`, `object`, `created` and `owned_by`, filtered by `type`
  and `sub_type`. There are no price fields.
- Free status and per-model rate limits are shown only on the web model
  catalogue (<https://cloud.siliconflow.cn/models>). The rate-limit guide says
  "the Rate Limits for free models are fixed" without listing them in the API.
- Account balance is available from `GET /v1/user/info`, but a non-zero
  balance would be spent by a paid model, so it cannot prove a call is free.

Guessing freeness from model ids (for example the `Pro/` prefix) could select a
paid model and spend your balance, so SiliconFlow is not supported until its
API exposes prices or a free flag.

- Sources: <https://docs.siliconflow.com/en/api-reference/models/get-model-list>
  (Chinese: <https://docs.siliconflow.com/cn/api-reference/models/get-model-list>),
  <https://docs.siliconflow.com/en/userguide/rate-limits/rate-limit-and-upgradation>,
  <https://docs.siliconflow.com/en/api-reference/userinfo/get-user-info>,
  <https://docs.siliconflow.com/en/faqs/error-code>.

## Using several providers

- Every enabled provider feeds one ranking. Each provider has its own API key
  variable (`OPENROUTER_API_KEY`, `GROQ_API_KEY`), its own probe cache file and
  daily counter, and its own rate-limit pause. A quota or account problem stops
  probing only for that provider.
- A provider without a key is skipped with a warning; if no provider has a
  key, `test`/`rank`/`sync` fail without sending anything.
- Fallbacks always come from the primary model's provider, because a target
  config has one base URL and one key.
- A target can be limited to the providers its tool has a key for with
  `options.providers: [openrouter]`. Without it the target may switch
  provider (and base URL); a warning is logged when several providers are
  enabled.
