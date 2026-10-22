# Contributing

Thanks for helping! Bug reports, new providers and new adapters are all welcome.

## Development setup

```bash
git clone https://github.com/ndwlbj/freemodel-sync
cd freemodel-sync
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check src tests
pytest
```

Python 3.9 is the oldest supported version; please do not use newer syntax
(ruff targets `py39`).

## Ground rules

- **Tests never touch the network.** Mock HTTP with `httpx.MockTransport`.
  Run tests with `OPENROUTER_API_KEY` unset; no test may spend real requests.
- **Never commit secrets or personal data**: API keys, tokens, webhook URLs,
  IP addresses, chat/user ids, your own configs or home paths. Use obvious
  placeholders (`vendor/model:free`, `example.com`).
- Every bug fix comes with a regression test.
- Keep changes focused; update `CHANGELOG.md` under *Unreleased* and both
  `README.md` and `README.zh-CN.md` when behaviour changes.

## Adding a provider

Subclass `freemodel_sync.providers.Provider`, implement `discover()` and
`test()` (and optionally `quota()`), decorate it with `@register_provider` and
add tests with recorded, anonymised API responses under `tests/fixtures/`.
A provider must:

- count a model as free only when it really costs nothing;
- tell account/quota errors (`failure_kind="account"`) apart from model
  failures, so a spent quota never marks every model as broken;
- never log the key.

## Adding an adapter

Subclass `freemodel_sync.adapters.base.Adapter`, implement `render()` and
register it with `@register_adapter`. The base class already handles diffs,
idempotency, backups and atomic writes. An adapter must leave everything it does
not manage untouched (keys, other entries, comments where possible) and should
be checked against the real tool's file format; say in the pull request which
version you checked.

## Pull requests

Fill in the pull request template. CI runs ruff, the test suite on Python
3.9-3.13 and with the minimum dependency versions, and a package build with
`twine check`.

## Releasing (maintainers)

Releases go to PyPI through `.github/workflows/release.yml` using
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub Actions
authenticates to PyPI with a short-lived OIDC token, so no PyPI API token is
stored anywhere.

**One-time setup**

1. On PyPI, add a *pending publisher* (Account settings → Publishing →
   Add a new pending publisher → GitHub) with:
   - PyPI project name: `freemodel-sync`
   - Owner: `ndwlbj`
   - Repository name: `freemodel-sync`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   After the first successful upload the pending publisher becomes a normal
   trusted publisher of the project.
2. In the GitHub repository settings, create an environment named `pypi`.
   Adding yourself as a required reviewer is recommended, so every upload
   needs a manual approval.

**Each release**

1. Bump `__version__` in `src/freemodel_sync/__init__.py`.
2. Move the *Unreleased* entries in `CHANGELOG.md` under a new
   `## [X.Y.Z] - YYYY-MM-DD` heading and update the compare links.
3. Merge to `main`, then create a GitHub release with the tag `vX.Y.Z`
   pointing at that commit and publish it. Publishing the release starts the
   workflow.
4. The build job checks out the tag, fails unless the tag without its
   leading `v` equals `__version__`, builds the sdist and wheel and runs
   `twine check --strict`. The publish job then uploads to PyPI, after the
   `pypi` environment approval if one is configured.

**Publishing an existing tag** (for example `v0.2.0`, released before this
workflow existed): Actions → *Release* → *Run workflow*, and enter the tag.
The same checks apply. PyPI never accepts the same version twice, so a
version that is already on PyPI cannot be re-uploaded.
