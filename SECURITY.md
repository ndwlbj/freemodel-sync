# Security policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately through GitHub:
[Security → Report a vulnerability](https://github.com/ndwlbj/freemodel-sync/security/advisories/new).
Include the version, what you ran, what happened and, if possible, a minimal
reproduction. Remove API keys, tokens, webhook URLs and personal paths from logs
before sending them.

You should get an acknowledgement within 7 days. Once a fix is released the
advisory will be published, crediting you unless you prefer otherwise.

## Scope

In scope, for example:

- an API key, bot token or webhook URL being written to a target file, a log,
  the cache/state file or a notification
- target files, backups or the cache being created with permissions that are
  too open, or written outside the configured path
- a probe or other request that can spend paid credits

Out of scope: vulnerabilities in OpenRouter, the tools whose configs are edited,
or your own environment (for example a world-readable env file).

## How freemodel-sync handles secrets

- Keys are read from environment variables only and are never written to config files.
- Log output is redacted; HTTP request logging is off unless `--debug-http` is given.
- Backups are created with mode 0600 or stricter.
