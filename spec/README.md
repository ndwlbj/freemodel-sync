# spec/: rules shared by the Python package and the dsh plugin

freemodel-sync has two implementations: the Python package (`src/freemodel_sync`,
CLI, AstrBot and other adapters, daily snapshot) and the dsh plugin
(`plugins/dsh-freemodel`, TypeScript). The rules they must agree on live here,
once, as JSON. Code is written twice; rules are written once.

| File | Content |
|---|---|
| `providers.json` | per provider: base URL, models path, key variable name, how "free" is decided, catalogue fields, probe request, **error classification** (`errorMap`), rate-limit headers, key formats, sources with the date they were checked |
| `ranking.json` | default ranking weights, score constants, non-chat model globs |
| `*.schema.json` | JSON Schema (2020-12) of the files above and of the conformance files |
| `state.schema.json` | format of the dsh plugin's state file `$DSH_HOME/freemodel/state.json` (catalogue cache, probe results, daily counters; never a key); `state.example.json` is a valid sample both test suites read |
| `conformance/*.json` | golden cases: input -> expected output, for classification, stream errors, the free rule, rate-limit headers, scores and the non-chat filter |

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

## Changing a rule

1. Edit the JSON here and bump nothing unless the format changes
   (`spec_version` changes only for incompatible format changes).
2. Add or update a case in `conformance/`.
3. Both runners must pass: `pytest tests/test_spec_conformance.py` and the
   plugin's `npm test` (`plugins/dsh-freemodel/test/conformance.test.ts`).

The files contain no keys or personal data; `tests/test_secret_guard.py`
checks this.
