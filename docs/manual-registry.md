# Manual tier-2 registry (ZCode / Qoder / WorkBuddy)

Some platforms have no public model/usage API: the only way to use them is
through their own dsh plugin, which owns the login and the model route. For
those platforms freemodel-sync offers a **manual registration** instead of a
provider integration. It records only public, non-sensitive facts and never
holds a credential.

The shared schema is [`spec/manual.schema.json`](../spec/manual.schema.json).
The dsh plugin's `manual[]` form and the Python `manual_providers` section are
two spellings of the same data.

## What goes in the config

Only the model id, an optional label/quota note and an optional expiry date:

```yaml
manual_providers:
  zcode:
    display_name: ZCode Start Plan (BigModel CN)
    auth: oauth_manual            # informational: dsh-zcode owns the login
    dsh_provider: dsh-zcode
    dsh_plugin: '@tnnevol/dsh-zcode'
    models:
      - id: glm-5.3
        tools: true
        quota: {unit: tokens, period: day, limit: 3000000}
```

The dsh plugin uses the camelCase form:

```json
{ "manual": [
  { "dshProvider": "dsh-zcode", "model": "glm-5.3",
    "label": "ZCode Start Plan", "quotaNote": "3M tokens/day",
    "expiresAt": "2026-12-31", "probe": false }
] }
```

Do **not** add `token`, `pat`, `cookie`, `password`, `secret` or `key` fields,
and do not paste a key-shaped string (`sk-...`, `gsk_...`, ...) into a label or
quota note. The Python loader and the plugin schema reject both. The only
`api_key_env` exception is for tier-1 `providers.*` entries, where the value is
an environment-variable *name*; manual registrations have no key field at all.

## ToS boundary

- The Python package **never** requests a ZCode, Qoder or WorkBuddy domain.
  `freemodel-sync registry list` and `registry check` read the local config and
  call no network at all.
- The only availability probe goes through dsh: our plugin calls the host's
  `ctx.llm` with the route registered by the user's own third-party plugin and
  a one-token "ping". This is equivalent to the user typing a message in dsh;
  the credential stays inside that plugin.
- We do not read third-party plugin routes for state, vault files or
  `/plugins/.../usage` endpoints, do not fake a client, and do not sign in or
  rotate accounts.
- Probing is off by default and needs **both** `manualProbe.enabled` and the
  entry's `probe: true`. One request per model per UTC day is a hard-coded cap;
  an `account` failure (for example WorkBuddy `11140`) stops that platform for
  the day, while `capacity` (queue / no capacity) is recorded without stopping
  the platform.
- Results live in the plugin state file and contain exactly
  `{provider, model, ok, failure_kind, error_code, tested_at}`. Error text is
  redacted and never stored; no key is written.

## Selection and CLI

Manual entries carry `tier: 2` and `source: manual` and are labelled
`手动，未核实`. They are excluded from automatic selection by default
(`filters.include_manual: false`). A target may opt in explicitly:

```yaml
targets:
  - adapter: openai-env
    path: ~/bot/.env
    options:
      providers: [zcode]   # explicitly allow this manual registration
```

`freemodel-sync registry list --json` shows each registration, its models,
expiry date and whether it is expired. `registry check --json` validates the
local section, reports expired entries/missing fields and returns without
contacting any platform.