# Changelog

All notable changes to the `dsh-freemodel` plugin are documented here. The
plugin is versioned separately from the Python `freemodel-sync` package.

## [Unreleased]

### Added

- **Alibaba Cloud Bailian channel (P8).** New `bailian` channel (route
  `freemodel-bailian`, `DASHSCOPE_API_KEY`, Beijing only), off by default. It
  lists and probes nothing until `freeQuotaGuardConfirmed` is ticked and
  `models` is non-empty. Models carry a hand-entered `quotaTokens` allowance
  shown as `手动，未核实` and never deducted from the probe budget; ids
  containing `distill` are marked `tools=false`. A 403
  `AllocationQuota.FreeTierOnly` is a `quota` failure that stops the channel
  until the next UTC day. Bailian is not part of the public daily snapshot.
- **`capacity` failures and ranking penalty (P8).** Queue / no-capacity probe
  results now use `failureKind: "capacity"`, the same short retry TTL as
  transient failures, and a separate consecutive counter in the state file.
  The picker penalty comes from `spec/ranking.json` (`capacity_penalty`); after
  `ranking.capacityDowngradeAfter` (default 3) consecutive results the model is
  no longer selectable. `quota` failures are kept out of the state results.
  New Vitest cases cover classification, TTL, the counter, the penalty and the
  downgrade, and the settings card can show a Bailian channel.

- **SenseNova Token Plan (P7).** New channel `sensenova` (route
  `freemodel-sensenova`, `SENSENOVA_API_KEY`), off by default. Nothing is listed or
  probed until `tokenPlanConfirmed` is ticked, because the public beta has no quota API
  and prices can change. An optional `models` allowlist is intersected with the
  catalogue when it can be read (an empty list means every catalogue model priced the
  string `"0"`); non-zero pricing is removed and logged. Capabilities are inferred from
  `supported_features` / `businesses` (vision, tools, reasoning), missing hints stay
  unknown. A 403 outside the plan is classified as a model failure; 401 is an account
  failure. SenseNova is not part of the public daily snapshot.

- **Capability and quota badges (P6).** Catalogue parsing now records
  `capabilities` (`tools`, `vision`, `reasoning`; `null` when the catalogue does
  not say) and an optional model-level `quota` using the shared `spec/` periods
  (`rolling_5h`, `week`, `day`, `total`, `beta`, `unknown`). Picker labels and
  descriptions append compact badges such as `工具`, `余 90k tokens · 5小时` or
  `公测期`; missing data shows `能力未知` / `额度未知` instead of a false zero.
  The pi-ai descriptor now passes through image input and reasoning when the
  catalogue reports them. Old state files without the new fields still load as
  unknown. The settings card's model rows show the same badges.

- **Settings card (P5).** A browser half (`src/client/`, built to
  `lib/client.js`, exported as `./client`, declared through `dsh.client`) with
  four tabs: overview, channels, models and diagnostics. It reads the local
  status route, shows key *presence* only, and lists every model with its probe
  state and reason when it is not listed. Channel switches, key references and
  ranking/refresh options remain in the host's schema form.
- **Per-model manual test.** Each model in the card has a **Test now** button
  that calls `POST /freemodel/api/test`. It sends one tiny probe and uses one
  free request from today's budget; disabled channels, missing keys and Groq
  without `freePlanConfirmed` are refused before any request.
- **`/freemodel` command and local API (P5 A).** `/freemodel status|refresh|
  test <channel> <model>` shows the same state in a conversation, and the
  loopback-only `/freemodel/api` prefix serves status, refresh and manual test
  with a JSON error envelope.
- **Build and tests.** `pnpm build` now also emits the `window.__ModuleLoader__`
  CJS wrapper for the card, with React required from the host runtime (no React
  dependency). New Vitest cases cover the client module loading, slot
  registration on the bundle/row seats, all four tabs, the Chinese copy, the
  manual-test callback and the API client's token/error handling.

### Security

- The on-disk API secret is never returned by any route. The loopback status
  document hands the settings card a separate process-local write token; it is
  not accepted from non-loopback peers and is never logged. The card keeps it
  in memory only and renders no provider key.

### Changed

- `LocalApiDeps` accepts an optional `clientKey` for the browser card. The
  existing header/bearer secret keeps working for CLI and API callers.
- The plugin README (English and Chinese) documents the card, the four tabs,
  the manual-test cost and the build outputs.

## [0.1.0] - 2026-10-27

- Initial private plugin skeleton: settings schema, free-model catalogue and
  probe service, `freemodel-openrouter` / `freemodel-groq` routes, state file,
  `status`/`doctor` CLI, bundled spec and host verification.