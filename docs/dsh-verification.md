# dsh adapter verification

Checked against **dsh 0.2.1-rc.2** with a throw-away DSH home (`HOME` and
`DSH_HOME` pointed at a temporary directory) using `dsh headless --dump-config`,
which prints the composed plugin configuration without starting a session or
calling any model. Telemetry was disabled.

| Check | Result |
| --- | --- |
| Adapter output passed as `--patch FILE` | Applied: the composed `agent-default-model` entry shows the new `provider`/`model` and is annotated `patched by FILE`. |
| Adapter-rewritten home `cordis.patch.yml` with another user entry and comments | Both entries are composed; the unmanaged entry and comments are preserved byte-for-byte. |
| Patch replaces the whole `config` mapping | Confirmed: keys not written by the patch are dropped. The adapter therefore carries over existing keys such as `reasoningEffort`. |
| `name` field | A wrong `name` makes dsh log `name mismatch ... skipping` and ignore the entry. No `name` or the correct `'@deepseek-ai/dsh-agent-default-model'` works. The adapter keeps an existing `name`; `entry_name` sets it. |
| Separate fallback entry (`fallback_entry_id`) | Rejected by dsh: `patch: entry "freemodel-fallbacks" not found`. The option is deprecated and ignored; dsh has no fallback list for the default model. |

Not verified: `--dump-config` does not check that the provider id exists in
your dsh setup or that the model is reachable. Use `provider_map` to match your
dsh provider id and run a real dsh session to confirm.

Notes from the dsh documentation: `settings.yaml` is only imported once from
older releases, so it does not override the model; Settings UI saves go to the
profile patch, and the home `cordis.patch.yml` and `--patch` overlays take
precedence over it.
