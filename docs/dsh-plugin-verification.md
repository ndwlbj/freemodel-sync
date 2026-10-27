# dsh plugin verification (plugins/dsh-freemodel 0.1.0, P4)

Checked on **2026-10-27** against **dsh 0.2.1-rc.3** (the `@deepseek-ai/dsh` CLI,
Node.js 22.23) with `plugins/dsh-freemodel/scripts/verify-host/verify-host.sh`.
The script is the reproducible form of this page; run it again after a dsh
upgrade:

```bash
cd plugins/dsh-freemodel
pnpm install --frozen-lockfile
scripts/verify-host/verify-host.sh            # or: verify-host.sh /path/to/dsh
```

## Isolation

Everything happens in a fresh `mktemp -d` work directory:

- `DSH_HOME` and `HOME` point inside it, so `~/.dsh`, its home
  `cordis.patch.yml`, its `.credentials.yaml`, every existing profile and every
  default model are untouched. The profile is a new `fm-dev` under the temporary
  `DSH_HOME`.
- The environment is cleared (`env -i`): no API keys, telemetry disabled
  (`DSH_TELEMETRY_DISABLED=1`, `DSH_TELEMETRY_MODE=DISABLED`,
  `OTEL_SDK_DISABLED=true`, OTLP URLs pointed at `127.0.0.1:9`). The working
  directory is an empty folder, because dsh also reads `<cwd>/.env` and
  `$DSH_HOME/.env` as credential fallbacks.
- In the default (offline) run no model is called. The host is started with no
  app plugin (no TUI, web or headless session); the probe stops it after its
  checks. The live run (below) is opt-in.
- The only key used is a fake one made at run time
  (`fms-verify-fake-<random hex>`). It is saved, read back and removed; the
  report records only booleans about it.

## Steps and results

| Step | Command | Result |
| --- | --- | --- |
| Build and pack | `pnpm run build`, `pnpm pack` | `dsh-freemodel-0.1.0.tgz`: `lib/`, `locale/`, `cordis.patch.yml`, `package.json`, `LICENSE`, `README.md` |
| Install | `dsh plugin --profile fm-dev add <tgz> scripts/verify-host/probe` | Profile created with bundles `@deepseek-ai/dsh-base`, `dsh-freemodel`, `dsh-freemodel-verify-probe`. pnpm warns that the peers (`cordis`, `schemastery`, `dsh-llm`, `dsh-llm-pi-ai`, `pi-ai`, `dsh-credentials`) may be missing: expected, the host provides them (same as first-party plugins). |
| Compatibility gate | (same) | Not skipped: `engines.dsh` `>=0.2.1-rc.1 <0.3.0-0` admits 0.2.1-rc.3. dsh's gate uses the package's own `engines.dsh` alone when present, and counts prereleases. |
| Composed profile | `dsh --profile fm-dev --dump-config` | The plugin's bundle patch is applied: `# == dsh-freemodel` / `- id: dsh-freemodel` / `name: dsh-freemodel` |
| CLI under the profile | `dsh plugin --profile fm-dev exec dsh-freemodel doctor` | `ok Node.js 22.23.4`, `ok dsh 0.2.1-rc.3 satisfies engines.dsh` (version read from `dsh --version`), `ok bundled spec_version 1`, `warn OPENROUTER_API_KEY is not set in this environment`, `doctor: no blocking problems` |
| Host boot | `dsh --profile fm-dev` (probe inside) | Exit 0 after the probe's SIGTERM; report `ok: true` |

The probe (`scripts/verify-host/probe/`, never published) runs inside the host
and uses the same services as the web settings page:

1. **Settings form.** `settings.describe({ redactSecrets: true })` lists only
   active plugin fibers, and has an entry `ns: "dsh-freemodel"` with
   `applies: "live"` and these fields:

   | Field | Type | Role | Default |
   | --- | --- | --- | --- |
   | `providers.openrouter.enabled` | boolean | | `true` |
   | `providers.openrouter.apiKeyEnv` | string | `credential-ref` | `OPENROUTER_API_KEY` |
   | `providers.groq.enabled` | boolean | | `false` |
   | `providers.groq.apiKeyEnv` | string | `credential-ref` | `GROQ_API_KEY` |
   | `providers.groq.freePlanConfirmed` | boolean | | `false` |

   The current value matches the defaults; `secrets` is empty (no field holds a
   secret, only variable names).
2. **Editing a credential-ref field.** `settings.update("dsh-freemodel",
   { providers: { openrouter: { apiKeyEnv: "FMS_VERIFY_OPENROUTER_KEY" } } }, 0)`
   moved the revision from 0 to 1, the live value changed with no restart, and the
   profile patch layer got an id-targeted `config` override for `dsh-freemodel`.
3. **Saving a key for that reference.** `credentials.describe` reported
   `{ configured: false, writable: true }`; after `credentials.set(ref, fake)` it
   reported `{ configured: true, source: "file", writable: true }` and `resolve`
   returned the same value from `file`. `$DSH_HOME/.credentials.yaml` was created
   with mode `600`. The settings entry still did not contain the value.
4. **Removing it.** After `credentials.unset(ref)`, `describe` reported
   `configured: false` again.

5. **Routes.** `llm.listConfigurableProviders()` has `freemodel-openrouter` and
   `freemodel-groq` (settings `dsh-freemodel` / `providers.<id>`). With no key
   in the environment `llm.listProviders()` has neither route; with a key only
   `freemodel-openrouter`. Groq is never registered (off, `freePlanConfirmed`
   false).

### Live run (opt-in)

```bash
FMS_VERIFY_LIVE=1 FMS_VERIFY_PROBES=2 OPENROUTER_API_KEY=... scripts/verify-host/verify-host.sh
```

Only `OPENROUTER_API_KEY` is passed through `env -i`; the profile gets
`refresh.probeTopN: 2`. Calls made: one catalogue read (`/models`, no key), one
`/key` check, `FMS_VERIFY_PROBES` probes and one chat of at most 256 tokens to
the top-ranked model, all `:free`. The report is checked for the key value
before it is written; a match replaces it with a verdict.

Result on 2026-10-27 (dsh 0.2.1-rc.3, real OpenRouter key from the box
environment, prefix `sk-or-v1-`):

| Step | Result |
| --- | --- |
| `llm-routes` | key `configured: true`, source `env`; registered `["freemodel-openrouter"]` |
| `live-listing` | catalogue 16 free candidates, no error; round: 2 probes, no stop reason; both passed (HTTP 200, TTFT 291 ms and 3061 ms) |
| Picker (`llm.listModels("freemodel-openrouter")`) | `NVIDIA: Nemotron 3.5 Lightning · 免费` (OpenRouter free · TTFT 291 ms · tools), `NVIDIA: Nemotron 3 Ultra · 免费` (TTFT 3061 ms) |
| `live-chat` | `nvidia/nemotron-3.5-lightning:free` answered `OK` in 2.2 s, finish `stop` |
| State file | `$DSH_HOME/freemodel/state.json`, mode `600`, no key |
| Leak check | key value not found in the work directory or the script output |

The first live attempt found a bug: the plugin read the `credentials` service
once at start, before it was active, and so saw no key. It now waits for it
with `ctx.inject(["credentials"], ...)` and re-checks the channels when it
appears or goes away.

Not checked here: the browser page itself (the profile has no web app), and the
plugin's own log line (`dsh-freemodel 0.1.0 mounted; ...`), which goes to dsh's
logger and has no console output in this headless boot. The unit tests cover that
line; the plugin being active is shown by step 1, since describe only lists
active fibers.

## Notes for later versions

- The plugin extends `PiAiAdapter` from `@deepseek-ai/dsh-llm-pi-ai` and uses the
  host's `@earendil-works/pi-ai` (checked with 1.4.0); both are peers and are
  not bundled.

- `engines.dsh` must be widened (and this check re-run) before dsh 0.3.0; dsh skips
  a bundle whose range does not match.
- The `dsh-freemodel` CLI imports no host package, so `dsh plugin exec` works
  although the peers are not installed in the profile. Outside a profile,
  `doctor` asks `dsh --version` (or takes `--dsh-version`).
