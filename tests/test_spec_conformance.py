"""Runs the shared golden cases in spec/conformance/ against the Python implementation.

The dsh plugin runs the same files with its own runner; if either side
disagrees with a case, its CI fails. See spec/README.md.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from freemodel_sync import spec
from freemodel_sync.models import Capabilities, ModelInfo, Quota, TestResult
from freemodel_sync.providers.bailian import BailianProvider
from freemodel_sync.providers.groq import GroqProvider
from freemodel_sync.providers.openai_compat import classify_status, classify_stream_error
from freemodel_sync.providers.openrouter import OpenRouterProvider, _is_free_model
from freemodel_sync.providers.sensenova import SenseNovaProvider
from freemodel_sync.ranking import RankWeights, is_non_chat, rank, score_model

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"
CONFORMANCE = SPEC / "conformance"

CLASSIFIERS = {
    "openrouter": OpenRouterProvider._classify,
    "groq": GroqProvider._classify,
    "sensenova": SenseNovaProvider._classify,
    "bailian": BailianProvider._classify,
    None: classify_status,
}
RATE_LIMITS = {"openrouter": OpenRouterProvider._rate_limit_hints, "groq": GroqProvider._rate_limit_hints}
PROVIDERS = {
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "sensenova": SenseNovaProvider,
    "bailian": BailianProvider,
}


def _cases(area):
    data = json.loads((CONFORMANCE / f"{area}.json").read_text(encoding="utf-8"))
    assert data["area"] == area
    return data


def _ids(cases):
    return [c.get("name") or c.get("id") for c in cases]


def _params(area):
    cases = _cases(area)["cases"]
    return pytest.mark.parametrize("case", cases, ids=_ids(cases))


# -- the spec files themselves ----------------------------------------------
def test_spec_files_validate_against_their_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    pairs = [
        ("providers.json", "providers.schema.json"),
        ("ranking.json", "ranking.schema.json"),
        ("state.example.json", "state.schema.json"),
    ]
    pairs += [(f"conformance/{p.name}", "conformance.schema.json") for p in sorted(CONFORMANCE.glob("*.json"))]
    for data_name, schema_name in pairs:
        schema = json.loads((SPEC / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(json.loads((SPEC / data_name).read_text(encoding="utf-8")), schema)


def test_state_schema_rejects_a_stored_key_field():
    """The plugin's state file has a closed schema, so a key field cannot slip in."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SPEC / "state.schema.json").read_text(encoding="utf-8"))
    state = json.loads((SPEC / "state.example.json").read_text(encoding="utf-8"))
    state["channels"]["openrouter"]["apiKey"] = "x"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(state, schema)


def test_every_conformance_file_has_a_runner():
    assert {p.stem for p in CONFORMANCE.glob("*.json")} == {
        "classify",
        "stream_classify",
        "free_rule",
        "rate_limit",
        "score",
        "non_chat",
        "capabilities",
        "quota",
        "capacity",
    }


def test_providers_take_their_constants_from_the_spec():
    for name, cls in PROVIDERS.items():
        entry = spec.provider_spec(name)
        assert cls.name == name
        assert cls.base_url == entry["baseURL"]
        assert cls.api_key_env == entry["apiKeyEnv"]
        assert cls.max_tokens_param == entry["probe"]["maxTokensParam"]


def test_spec_is_read_from_the_repository_in_a_checkout():
    assert spec.spec_dir() == SPEC


def test_spec_version_mismatch_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "providers.json").write_text(json.dumps({"spec_version": 99}), encoding="utf-8")
    monkeypatch.setattr(spec, "spec_dir", lambda: tmp_path)
    with pytest.raises(spec.SpecError, match="spec_version 99"):
        spec._load("providers.json")


def test_unreadable_spec_is_an_error(tmp_path, monkeypatch):
    (tmp_path / "providers.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(spec, "spec_dir", lambda: tmp_path)
    with pytest.raises(spec.SpecError, match="cannot read"):
        spec._load("providers.json")


def test_missing_spec_dir_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(spec, "__file__", str(tmp_path / "a" / "b" / "spec.py"))
    with pytest.raises(spec.SpecError, match="not found"):
        spec.spec_dir()


def test_unknown_condition_is_an_error():
    error_map = {"preStream": [{"status": [403], "when": [{"bogus": "x"}], "kind": "model"}], "default": "model"}
    with pytest.raises(spec.SpecError, match="unknown condition"):
        spec.classify_with(error_map, 403, {})


def test_no_status_falls_back_to_default():
    assert spec.classify_with(spec.default_error_map(), None, {}) == "model"


def test_every_spec_key_pattern_is_redacted():
    """Key formats in providers.json are masked by freemodel_sync.redact."""

    import re

    from freemodel_sync.redact import redact

    samples = {
        "sk-or-": "sk-or-v1-" + "0123456789abcdef" * 4,
        "gsk_": "gsk_" + "Ab1" * 18,
        "sk-": "sk-" + "A1b2C3d4" * 4,
        "sk-ws-": "sk-ws-" + "A1b2C3d4" * 14,
    }
    for name in PROVIDERS:
        for pattern in spec.provider_spec(name)["keyPatterns"]:
            sample = samples[pattern["prefix"]]
            assert re.search(pattern["regex"], sample), (name, pattern)
            assert sample not in redact(sample)


# -- golden cases ---------------------------------------------------------------
@_params("capabilities")
def test_capabilities(case):
    got = Capabilities.from_dict(case["input"], supports_tools=case.get("supportsTools")).to_dict()
    assert got == case["expected"]


@_params("quota")
def test_quota(case):
    quota = Quota.from_dict(case["input"])
    got = {
        "unit": quota.unit,
        "period": quota.period,
        "window_seconds": quota.window_seconds,
        "remaining_window": quota.remaining_window,
        "remaining_today": quota.remaining_today,
        "remaining_total": quota.remaining_total,
        "is_exhausted": quota.is_exhausted,
    }
    assert got == case["expected"]


@_params("classify")
def test_classify(case):
    error = case["error"] if isinstance(case["error"], dict) else {}
    assert CLASSIFIERS[case["provider"]](case["status"], error) == case["expected"]


@_params("stream_classify")
def test_stream_classify(case):
    got = classify_stream_error(case["code"], case["error"], classify=CLASSIFIERS[case["provider"]])
    assert got == case["expected"]


def _sensenova_free(case):
    plan = str(case.get("plan") or "").strip().lower().replace("_", "-").replace(" ", "-")
    if plan != spec.provider_spec("sensenova")["freeRule"]["value"]:
        return False
    model = case.get("model")
    if not isinstance(model, dict):
        return True
    pricing = model.get("pricing")
    return isinstance(pricing, str) and pricing.strip() == "0"


def _bailian_free(case):
    guard = str(case.get("guard") or "").strip().lower()
    if guard != spec.provider_spec("bailian")["freeRule"]["guardValue"]:
        return False
    model = case.get("model")
    model_id = model.get("id") if isinstance(model, dict) else None
    return isinstance(model_id, str) and model_id in (case.get("models") or [])


@_params("free_rule")
def test_free_rule(case):
    if case["provider"] == "openrouter":
        assert _is_free_model(case["model"]) is case["expected"]
    elif case["provider"] == "sensenova":
        assert _sensenova_free(case) is case["expected"]
    elif case["provider"] == "bailian":
        assert _bailian_free(case) is case["expected"]
    else:  # pragma: no cover - a new provider needs its own runner branch
        raise AssertionError(f"no free-rule runner for {case['provider']}")


@_params("rate_limit")
def test_rate_limit(case):
    retry_after, remaining = RATE_LIMITS[case["provider"]](case["headers"])
    expected = case["expected"]
    if expected["retryAfterS"] is None:
        assert retry_after is None
    else:
        assert retry_after == pytest.approx(expected["retryAfterS"], abs=1e-6)
    assert remaining == expected["remaining"]


def _model(raw):
    raw = dict(raw)
    expiration = raw.pop("expiration_date", None)
    return ModelInfo(
        "openrouter",
        name=raw["id"],
        expiration_date=date.fromisoformat(expiration) if expiration else None,
        **raw,
    )


def _test(model, raw):
    if raw is None:
        return None
    return TestResult(
        key=model.key,
        ok=raw["ok"],
        ttft_ms=raw.get("ttft_ms"),
        failure_kind=raw.get("failure_kind"),
        capacity_streak=raw.get("capacity_streak", 0),
        error=raw.get("error"),
        status_code=raw.get("status_code"),
    )


_SCORE = _cases("score")
_TODAY = date.fromisoformat(_SCORE["today"])


@pytest.mark.parametrize("case", _SCORE["cases"], ids=_ids(_SCORE["cases"]))
def test_score(case):
    model = _model(case["model"])
    score, reasons = score_model(model, _test(model, case["test"]), RankWeights(), today=_TODAY)
    assert score == pytest.approx(case["expected"]["score"], abs=1e-6)
    assert reasons == case["expected"]["reasons"]


def test_rank_order():
    models = [_model(c["model"]) for c in _SCORE["cases"]]
    results = {}
    for model, case in zip(models, _SCORE["cases"], strict=True):
        result = _test(model, case["test"])
        if result is not None:
            results[model.key] = result
    assert [r.model.id for r in rank(models, results, today=_TODAY)] == _SCORE["rankOrder"]


@_params("capacity")
def test_capacity(case):
    if case["kind"] == "classify":
        error = case["error"] if isinstance(case["error"], dict) else {}
        assert CLASSIFIERS[case["provider"]](case["status"], error) == case["expected"]
        return
    model = _model(case["model"])
    test = _test(model, case["test"])
    score, reasons = score_model(
        model,
        test,
        RankWeights(),
        today=_TODAY,
        capacity_downgrade_after=spec.ranking_spec()["capacity"]["downgradeAfter"],
    )
    assert score == pytest.approx(case["expected"]["score"], abs=1e-6)
    assert reasons == case["expected"]["reasons"]


@_params("non_chat")
def test_non_chat(case):
    assert is_non_chat(ModelInfo("openrouter", case["id"], name=case["name"])) is case["expected"]
