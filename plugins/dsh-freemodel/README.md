# dsh-freemodel

[English](README.md) | [简体中文](README.zh-CN.md)

A [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) plugin for free models from OpenRouter (`:free` models) and, opt-in, Groq's free plan, the SenseNova Token Plan public beta, and Alibaba Cloud Bailian. It is the dsh runtime component of [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) and shares rules directly from the repository's `spec/` directory (bundled at build time).

> [!NOTE]
> - **Release status**: Version 1.0.0 (private; **not published to npm**).
> - **Screenshots**: Placeholders; real ones pending real-device UI capture.
> - **Real-device test status**: Verified on Linux with dsh 0.2.1-rc.3; **not run: Windows/macOS real-device tests**.
> - **Profile layout disclaimer**: Current-profile patch path is assumed at `$DSH_HOME/profiles/<id>/cordis.patch.yml` — layout not verified on a real dsh.

---

## Features

- **Multi-channel free models**: Aggregates verified free models across OpenRouter, Groq, SenseNova, and Bailian into distinct routes: `freemodel-openrouter`, `freemodel-groq`, `freemodel-sensenova`, and `freemodel-bailian`.
- **Badged in picker**: Free models appear in dsh's model picker labelled `· 免费`, accompanied by compact capability and quota badges (e.g. `· 工具 · 视觉 · 余 90k tokens · 5小时`). Unknown fields show `能力未知` / `额度未知` instead of false claims.
- **Fail-safe probing**: Probes candidates with tiny requests before listing. Failing models are hidden from the picker; failure reasons are recorded in `$DSH_HOME/freemodel/state.json` (file mode 0600, never contains keys) and inspectable via status commands.
- **Capacity failure handling**: Queue and capacity errors (`capacity`) receive short retry TTLs, separate streak counters, ranking penalties, and downgrade after successive failures.
- **Optional `freemodel-auto` route**: Opt-in `freemodel-auto` (`best`) route dynamically routes to the highest-ranked free model, with in-process failover to the next ranked candidate before any visible text is output.
- **Optional `autoDefaultModel` switch**: Opt-in switch for the profile's default model (`agent-default-model`), guarded against touching QQ/bot profiles and the root home patch layer.
- **Tier-2 manual registry**: Track external models (ZCode, Qoder, WorkBuddy) with public metadata only. No secrets or tokens stored. Opt-in probing capped at 1 probe per model per UTC day.
- **Interactive settings card**: A five-tab UI card in dsh's Settings panel for live overview, channels, models, manual registry, and diagnostics, with per-model test buttons.
- **Built-in CLI & Slash command**: Inspect state via `dsh-freemodel status` / `doctor` or in chat via `/freemodel`.

---

## Quick Start & Installation

### Prerequisites

- Node.js `^22.19.0 || >=24.0.0`
- pnpm `^10.0.0`
- dsh `>=0.2.1-rc.1 <0.3.0-0`

### Build & Pack

```bash
# From this directory: plugins/dsh-freemodel
pnpm install --frozen-lockfile
pnpm run check            # typecheck + unit tests + build
pnpm run build && pnpm pack

# Install into a dsh test profile
dsh plugin --profile <test-profile> add ./dsh-freemodel-1.0.0.tgz
dsh plugin --profile <test-profile> exec dsh-freemodel doctor
```

`pnpm build` bundles `lib/index.js` (plugin runtime), `lib/bin.js` (CLI), and `lib/client.js` (settings card web bundle).

### Setting Up API Keys

Provider keys are **never** stored in the plugin's configuration file. Each channel references an environment variable name (e.g. `OPENROUTER_API_KEY`). You can either:
1. Enter the key in dsh's Settings UI under Credentials (stored securely in `$DSH_HOME/.credentials.yaml` with mode 0600), or
2. Export the environment variable before launching dsh:
   ```bash
   export OPENROUTER_API_KEY="your-openrouter-key"
   ```

#### Headless profiles / no credential store

Headless dsh profile templates often omit or disable the local credentials service (`@deepseek-ai/dsh-credentials-local`). When no credential store is present or when it has no value for a key, the plugin automatically falls back to `process.env[apiKeyEnv]` (e.g. `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `SENSENOVA_API_KEY`, `DASHSCOPE_API_KEY`). Set the variable in the environment that starts dsh. The credential store still takes priority when a value is configured, and the plugin reports the source as `env` in status/doctor without ever logging or printing the key value.

---

## Supported Channels

| Channel | Route | Default | Required Confirmation / Guards | Key Reference |
| --- | --- | --- | --- | --- |
| **OpenRouter** | `freemodel-openrouter` | **Enabled** (if key set) | Only lists `:free` models from catalogue. | `OPENROUTER_API_KEY` |
| **Groq** | `freemodel-groq` | Disabled | Requires `freePlanConfirmed: true`. Account-level free tier. | `GROQ_API_KEY` |
| **SenseNova** | `freemodel-sensenova` | Disabled | Requires `tokenPlanConfirmed: true` (Token Plan public beta). Price must be `"0"`. Optional `models` allowlist. | `SENSENOVA_API_KEY` |
| **Bailian** | `freemodel-bailian` | Disabled | Requires `freeQuotaGuardConfirmed: true` (console guard) and non-empty `models` allowlist. Beijing region only. Quota is manual/unverified. 403 `FreeTierOnly` halts channel for the day. | `DASHSCOPE_API_KEY` |

---

## Configuration Reference

Settings can be edited in dsh's Settings &rarr; Plugins &rarr; DSH FreeModel configuration panel:

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `providers.<channel>.enabled` | `boolean` | `true` (openrouter)<br>`false` (others) | Enable or disable the channel. |
| `providers.<channel>.apiKeyEnv` | `string` | Per-channel default | Name of the environment variable containing the provider API key. |
| `providers.groq.freePlanConfirmed` | `boolean` | `false` | Must be ticked to confirm your Groq account is on the free plan. |
| `providers.sensenova.tokenPlanConfirmed` | `boolean` | `false` | Must be ticked to confirm enrollment in SenseNova Token Plan beta. |
| `providers.sensenova.models` | `string[]` | `[]` | Optional allowlist. If empty, all models with price `"0"` are candidates. |
| `providers.bailian.freeQuotaGuardConfirmed` | `boolean` | `false` | Must be ticked to confirm "stop when free quota exhausted" in Bailian console. |
| `providers.bailian.models` | `array` | `[]` | List of allowed model objects `{ id, quotaTokens }`. Hand-entered token limits are marked unverified. |
| `autoRoute.enabled` | `boolean` | `false` | Enables `freemodel-auto` (`best`) route with in-process failover. |
| `autoDefaultModel` | `boolean` | `false` | Opt-in switch for profile's default model (`agent-default-model`). Guarded. |
| `ranking.weights.*` | `number` | Spec defaults | Scoring weights for TTFT, context length, tools, vision, and reasoning. |
| `ranking.capacityPenalty` | `number` | `20` | Score deduction per consecutive capacity failure streak. |
| `ranking.capacityDowngradeAfter` | `number` | `3` | Streak threshold after which a capacity-failing model is excluded. |
| `refresh.intervalM` | `number` | `60` | Background probe and catalogue refresh interval in minutes. |
| `refresh.maxTestsPerRound` | `number` | `5` | Maximum active probes performed per channel refresh cycle. |
| `refresh.dailyReserve` | `number` | `10` | Daily request reserve kept untouched to avoid hitting hard limits. |
| `manual[]` | `array` | `[]` | Tier-2 manual registry entries (ZCode, Qoder, WorkBuddy). |
| `manualProbe.enabled` | `boolean` | `false` | Global switch for opt-in single-ping probing of manual entries. |

---

## Safety Rules & Guardrails

1. **Zero Secret Leakage**:
   - Provider keys are resolved dynamically through dsh's `ctx.credentials` service.
   - Settings files and state documents (`$DSH_HOME/freemodel/state.json`) **never** store keys.
   - Error messages redact any detected credential strings before logging or caching.
   - In documentation and tests, fake keys avoid key-like formats (`sk-` followed by 20+ characters is prohibited).

2. **Default Model Guardrails (`autoDefaultModel`)**:
   - **Off by default**: Must be explicitly activated by setting `autoDefaultModel: true`.
   - **QQ / Bot Profile Protection**: Modifying default models on QQ or chat bot profiles is strictly denied. Any profile name matching `/qq|bot|astrbot|napcat|onebot/i` is refused and skipped.
   - **Home Layer Protection**: Modifying `$DSH_HOME/cordis.patch.yml` is strictly forbidden. The plugin only targets individual profile patches.
   - **Environment Authorization**: Even when enabled in configuration, write operations require the environment flag `DSH_FREEMODEL_APPLY_DEFAULT=1`. Without this flag, the plugin logs `would-write` and takes no disk action.
   - **Profile Layout Disclaimer**: Profile patches are assumed to be located at `$DSH_HOME/profiles/<id>/cordis.patch.yml`. This directory structure is based on standard conventions but is not verified across all real dsh installations.

3. **Auto-Route Failover Rules (`freemodel-auto`)**:
   - Targets the current #1 ranked model among probe-verified channel models.
   - **Pre-output failover**: If a candidate model fails with a terminal error or stream error *before* any visible text deltas have been emitted, the adapter seamlessly switches to the next ranked candidate.
   - **No mid-stream failover**: Once any visible text token has been yielded to the caller, failover is blocked to prevent garbled or contradictory responses. Subsequent stream errors are terminal.
   - Manual (tier-2) models are **never** included in `freemodel-auto`.

4. **Loopback & API Isolation**:
   - The embedded HTTP service (`/freemodel/api/*`) binds exclusively to loopback addresses (`127.0.0.1`, `::1`).
   - Write actions (manual test invocation, cache invalidation) require authentication: CLI callers use an on-disk secret file (mode 0600), while web cards use an ephemeral in-process token provided via the loopback status payload.

---

## Tier-2 Manual Registry

The `manual[]` configuration allows users to document models made available by third-party plugins (e.g. ZCode, Qoder, WorkBuddy) without reverse engineering or proxying:

- **Public metadata only**: Accepts `provider`, `model`, `displayName`, `quotaNotes`, and `expiresAt`.
- **Secret rejection**: The schemastery schema and parser strictly reject any credential fields (`token`, `apiKey`, `password`, `cookie`, `secret`, `pat`) or values shaped like API keys.
- **No automatic selection**: Manual models are not eligible for `freemodel-auto` or automatic ranking.
- **Conservative probing**: If both `manualProbe.enabled` and the entry's `probe: true` are enabled, the plugin issues a single non-streaming `ping` message via `ctx.llm`. Hard-capped at 1 probe per model per UTC day. If an account-level error (e.g. WorkBuddy `11140`) occurs, probing for that platform is paused for the remainder of the UTC day.

---

## Settings Card & UI

The browser extension (`lib/client.js`) attaches a comprehensive management card to the DSH FreeModel settings page with five functional tabs:

1. **Overview**: Displays plugin version (`1.0.0`), spec version, state file path, active channels, model counts, and probe budget consumption.
2. **Channels**: Channel activation states, credential source (`file`, `env`), endpoint URLs, catalogue refresh timestamps, and rate-limit backoffs.
3. **Models**: Lists all verified models with badges (tools, vision, reasoning, quota) and TTFT latency. Shows unlisted/hidden models with exact failure reasons. Features a **Test now** button for each model.
4. **Manual**: Shows configured tier-2 entries, detection status of corresponding dsh routes, expiration status, and last probe results.
5. **Diagnostics**: Schema versions, local API endpoint prefix, error logs, and troubleshooting guidance.

> [!NOTE]
> **Screenshots**: The settings-card screenshot is a placeholder kept in the repo only and not part of the npm package yet (real ones pending real-device UI capture). The reference image is located at `docs/assets/dsh-freemodel-settings-card-placeholder.png` and declared in `screenshots.json`.

---

## CLI & Slash Commands

### Command Line Interface

Run commands using `dsh plugin exec`:

```bash
# Print status summary (channels, models, keys, state file)
dsh plugin --profile <profile> exec dsh-freemodel status

# Output machine-readable JSON status
dsh plugin --profile <profile> exec dsh-freemodel status --json

# Run runtime environment diagnostics (Node version, dsh version, spec conformance)
dsh plugin --profile <profile> exec dsh-freemodel doctor
```

### In-Chat Slash Command

Inside any dsh conversation:

- `/freemodel`: Display current status summary.
- `/freemodel refresh`: Force an immediate catalogue reload and probe pass.
- `/freemodel test <channel> <model>`: Run a single probe on a specific model.

---

## Troubleshooting

- **Models not appearing in picker**:
  - Run `dsh-freemodel status` to check if the channel key is detected.
  - Check the **Models** tab in the settings card for rejection reasons (e.g. probe timeout, catalogue error, capacity downgrade).
  - For Groq, ensure `freePlanConfirmed` is checked.
  - For SenseNova, ensure `tokenPlanConfirmed` is checked.
  - For Bailian, ensure `freeQuotaGuardConfirmed` is checked and `models` has at least one entry.
- **Probe stopped early**:
  - The plugin respects `refresh.maxTestsPerRound` (default 5) and `refresh.dailyReserve` (default 10 requests reserved for user chats).
- **Default model did not switch**:
  - Check whether `autoDefaultModel` is enabled.
  - Ensure the target profile is not named after a bot (`qq`, `bot`, `astrbot`, etc.).
  - Ensure the environment variable `DSH_FREEMODEL_APPLY_DEFAULT=1` is exported.
- **Real-device test note**:
  - Verified on Linux with dsh 0.2.1-rc.3.
  - Not run: Windows/macOS real-device tests.

---

## License

MIT
