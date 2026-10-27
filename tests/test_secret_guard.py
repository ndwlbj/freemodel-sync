"""P1 secret guard: redaction of every supported key format, exact-value
redaction of the keys a run uses, the gitleaks rules and a scan of the
repository's documentation, examples, spec and plugin files.

No literal key appears in this file: fake keys are built at runtime, so the
repository's own secret scan stays clean.
"""

from __future__ import annotations

import logging
import re
import string
from pathlib import Path

import pytest
import yaml

from freemodel_sync import redact as redact_mod
from freemodel_sync.cli import RedactingFilter, _resolve_providers
from freemodel_sync.config import Config, ProviderConfig
from freemodel_sync.redact import KEY_PATTERNS, redact, register_secret

ROOT = Path(__file__).resolve().parents[1]
ALNUM = string.ascii_letters + string.digits


def _fill(alphabet: str, n: int) -> str:
    return "".join(alphabet[(i * 7 + 3) % len(alphabet)] for i in range(n))


#: realistic shapes of each provider's keys (fake values)
FAKE_KEYS = {
    "openrouter": "sk-or-v1-" + _fill("0123456789abcdef", 64),
    "groq": "gsk_" + _fill(ALNUM, 52),
    "sensenova": "sk-" + _fill(ALNUM, 32),
    "dashscope-ws": "sk-ws-" + _fill(ALNUM + "._-", 111),
    "dashscope-sp": "sk-sp-" + _fill(ALNUM, 32),
    "dashscope": "sk-" + _fill("0123456789abcdef", 32),
}


@pytest.mark.parametrize("kind", sorted(FAKE_KEYS))
def test_every_key_format_is_masked_whole(kind):
    key = FAKE_KEYS[kind]
    text = redact(f"upstream said: invalid key {key}, try again")
    assert key not in text
    # no tail of the key survives either (e.g. after a '.' inside a sk-ws- key)
    assert key[-12:] not in text
    assert "<redacted>" in text
    assert text.endswith(", try again")


def test_prefix_is_kept_so_logs_say_which_key():
    assert redact(FAKE_KEYS["dashscope-ws"]) == "sk-ws-<redacted>"
    assert redact(FAKE_KEYS["openrouter"]) == "sk-or-<redacted>"
    assert redact(FAKE_KEYS["groq"]) == "gsk_<redacted>"


def test_bearer_and_authorization_headers():
    assert redact("Authorization: Bearer abc.def-123") == "Authorization: Bearer <redacted>"
    assert "opaque-token-value" not in redact("headers={'authorization': 'opaque-token-value'}")


def test_registered_values_are_masked_whatever_their_shape():
    odd = "custom" + _fill(ALNUM, 20)  # no known prefix
    assert odd in redact(f"x {odd} y")
    register_secret(odd)
    assert redact(f"x {odd} y") == "x <redacted> y"


def test_short_values_are_not_registered():
    register_secret("abc")
    register_secret(None)
    register_secret("")
    assert redact("abc abc") == "abc abc"
    assert redact_mod.registered_secrets() == ()


def test_longest_registered_value_wins():
    inner = "inner" + _fill(ALNUM, 10)
    outer = "outer-" + inner + "-tail"
    register_secret(inner)
    register_secret(outer)
    assert redact(outer) == "<redacted>"


def test_cli_registers_the_api_key_it_reads(monkeypatch):
    odd = "unprefixed" + _fill(ALNUM, 24)
    monkeypatch.setenv("FMS_TEST_KEY", odd)
    config = Config(providers={"openrouter": ProviderConfig(enabled=True, api_key_env="FMS_TEST_KEY")})
    _resolve_providers(config, provider_factory=lambda name, api_key=None, **o: object())
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, "request failed for %s", (odd,), None)
    RedactingFilter().filter(record)
    assert odd not in record.getMessage()


def test_cli_and_snapshot_share_the_patterns():
    import importlib.util

    spec = importlib.util.spec_from_file_location("daily_snapshot", ROOT / "scripts" / "daily_snapshot.py")
    assert spec and spec.loader
    ds = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ds)
    assert ds._REDACT_PATTERNS is KEY_PATTERNS is RedactingFilter._PATTERNS
    assert FAKE_KEYS["dashscope-ws"] not in ds.redact(FAKE_KEYS["dashscope-ws"])


# -- gitleaks configuration ----------------------------------------------------
def _gitleaks_rules():
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    return tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))


def test_gitleaks_extends_the_default_rules():
    config = _gitleaks_rules()
    assert config["extend"]["useDefault"] is True


@pytest.mark.parametrize("kind", sorted(FAKE_KEYS))
def test_gitleaks_custom_rules_catch_every_key_format(kind):
    rules = _gitleaks_rules()["rules"]
    # the rules use RE2 syntax that Python's re also accepts
    assert any(re.search(rule["regex"], f'key = "{FAKE_KEYS[kind]}"') for rule in rules), kind


def test_ci_runs_a_pinned_gitleaks_scan():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    job = jobs["secret-scan"]
    steps = job["steps"]
    checkout = steps[0]
    assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", checkout["uses"])
    assert checkout["with"]["fetch-depth"] == 0 and checkout["with"]["persist-credentials"] is False
    install = next(s for s in steps if "gitleaks" in s.get("name", "").lower() and "env" in s)
    assert re.fullmatch(r"\d+\.\d+\.\d+", install["env"]["GITLEAKS_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", install["env"]["GITLEAKS_SHA256"])
    assert "sha256sum -c" in install["run"]
    scan = steps[-1]["run"]
    assert "--config .gitleaks.toml" in scan and "--redact" in scan


# -- repository content --------------------------------------------------------
#: directories whose files are published as-is and must never carry a key
SCANNED_DIRS = ("examples", "docs", "plugins", "spec")
SCANNED_ROOT_FILES = ("README.md", "README.zh-CN.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md")
SKIP_PARTS = {"node_modules", "dist", "lib", ".turbo", "coverage"}


def _scanned_files():
    for name in SCANNED_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not SKIP_PARTS.intersection(path.relative_to(ROOT).parts):
                yield path
    for name in SCANNED_ROOT_FILES:
        if (ROOT / name).is_file():
            yield ROOT / name


def _key_like(text: str):
    for pattern, _replacement in KEY_PATTERNS:
        for match in pattern.finditer(text):
            found = match.group(0)
            # "Bearer <placeholder>", "sk-or-..." and similar documentation stand-ins are fine
            if "<" in found or "..." in found or "…" in found:
                continue
            if re.search(r"(?i)bearer\s|authorization|telegram", found):
                continue
            yield found


def test_published_files_contain_no_key_like_strings():
    offenders = []
    for path in _scanned_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for found in _key_like(text):
            offenders.append(f"{path.relative_to(ROOT)}: {found[:8]}...")
    assert not offenders, offenders


def test_repo_scan_would_catch_a_planted_key(tmp_path):
    planted = f"api_key: {FAKE_KEYS['sensenova']}\n"
    assert list(_key_like(planted))
