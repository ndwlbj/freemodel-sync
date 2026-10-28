# Changelog

All notable changes to the `dsh-freemodel` plugin are documented here. The
plugin is versioned separately from the Python `freemodel-sync` package.

## [Unreleased]

### Added

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