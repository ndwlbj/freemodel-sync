# spec/: rules shared by the Python package and the dsh plugin

freemodel-sync has two implementations: the Python package (`src/freemodel_sync`,
CLI, AstrBot and other adapters, daily snapshot) and the dsh plugin
(`plugins/dsh-freemodel`, TypeScript). The rules they must agree on live here,
once, as JSON. Code is written twice; rules are written once.

| File | Content |
|---|---|
| `providers.json` | per provider: base URL, models path, key variable name, how "free" is decided, catalogue fields, **capabilities** and the generic **quota** vocabulary, probe request, **error classification** (`errorMap`), rate-limit headers, key formats, sources with the date they were checked |
| `ranking.json` | default ranking weights, score constants, non-chat model globs |
| `*.schema.json` | JSON Schema (2020-12) of the files above and of the conformance files |
| `state.schema.json` | format of the dsh plugin's state file `$DSH_HOME/freemodel/state.json` (catalogue cache, probe results, daily counters and the six-field manual-probe records; never a key); `state.example.json` is a valid sample both test suites read |
| `manual.schema.json` | tier-2 manual registration: the dsh plugin's `manual[]` and Python's `manual_providers`; rejects secret-bearing keys and key-shaped values |
| `conformance/*.json` | golden cases: input -> expected output, for classification, stream errors, the free rule, rate-limit headers, scores, `capacity`, the non-chat filter, capability parsing, quota normalisation and the manual registry/probe rules |

## Capabilities and quota

`providers.json` has two shared vocabularies:

- `capabilities.fields` (`tools`, `vision`, `reasoning`) and
  `capabilities.sources` (`catalog`, `config`, `probe`, `manual`, `unknown`).
  A missing or unrecognised flag is `null` (unknown), never `false`.
  Per-provider `capabilities` entries say which catalogue field supplies each
  flag, or `null` when the catalogue does not say.
- `quota.units` (`requests`, `tokens`, `credits`, `unknown`),
  `quota.periods` (`rolling_5h`, `week`, `day`, `total`, `beta`, `unknown`),
  fixed `periodSeconds` for the timed windows, and `quota.sources` /
  `quota.scopes`. Numbers are optional: a missing value stays unknown, and a
  computed remaining value is conservative (probes sent after the snapshot are
  subtracted for provider data, not for manual values).

The Python `Quota`/`Capabilities` classes and the plugin's `parseQuota` /
`parseCapabilities` both read these forms, including old documents without the
new fields.

## Error rules (`errorMap`)

`preStream` rules are tried in order; the first rule whose `status` list
(or `statusMin`) matches and one of whose `when` conditions holds gives the
failure kind. A rule without `when` always matches its statuses. Conditions
read dotted paths in the upstream error object:

- `{"truthy": "metadata.limit_source"}`: the value is present and not empty/0/false
- `{"notNull": "metadata.provider_code"}`: the value is present (0 counts)
- `{"in": "metadata.error_type", "values": [...]}`: the value is one of `values`

No match gives `default`. Errors inside the SSE stream follow `streamError`
(the same algorithm for every provider).

Kinds are `model`, `transient`, `account`, `capacity` and `quota`.
`capacity` means queued / no capacity: it uses the short transient TTL but has
its own consecutive counter (`capacity_streak` / `capacityStreak`), gets the
`weights.capacity_penalty` score, and is treated as failed after
`capacity.downgradeAfter` in a row. `quota` means the free allowance is gone
for the day (Bailian's `AllocationQuota.FreeTierOnly`); the channel stops until
the next UTC day and the result is not stored as a model failure.

## Manual tier-2 registration

`manual.schema.json` covers both spellings: the plugin's `manual[]` entries
(`dshProvider`, `model`, `label`, `quotaNote`, `expiresAt`, `probe`) and the
Python `manual_providers` mapping (`display_name`, `auth`, `dsh_provider`,
`dsh_plugin`, `models[]`). It rejects `token`/`pat`/`cookie`/`password`/
`secret`/`key` fields and key-shaped values. The Python side never probes these
platforms; the plugin may probe through `ctx.llm` only when the global switch
and the entry opt-in are both on, at most once per model per UTC day. An
`account` failure stops that platform for the day; `capacity` is recorded but
does not stop it. `conformance/manual.json` pins these rules for both runners.

## Changing a rule

1. Edit the JSON here and bump nothing unless the format changes
   (`spec_version` changes only for incompatible format changes).
2. Add or update a case in `conformance/`.
3. Both runners must pass: `pytest tests/test_spec_conformance.py` and the
   plugin's `npm test` (`plugins/dsh-freemodel/test/conformance.test.ts`).

The files contain no keys or personal data; `tests/test_secret_guard.py`
checks this.
