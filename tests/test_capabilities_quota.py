"""Capabilities and the generic quota (P6): unknown stays unknown, old data still reads."""

from __future__ import annotations

from freemodel_sync import spec
from freemodel_sync.cli import RANKING_SCHEMA_VERSION, _ranking_payload
from freemodel_sync.models import Capabilities, ModelInfo, Quota, QuotaInfo


def test_missing_or_unrecognised_capabilities_are_unknown():
    for raw in (None, {}, {"tools": "?", "vision": "n/a", "source": "nowhere"}):
        assert Capabilities.from_dict(raw).to_dict() == {
            "tools": None,
            "vision": None,
            "reasoning": None,
            "source": "unknown",
        }


def test_capabilities_keep_known_flags_and_legacy_supports_tools():
    caps = Capabilities.from_dict({"tools": None, "vision": True, "reasoning": "unknown", "source": "catalog"})
    assert caps.tools is None and caps.vision is True and caps.reasoning is None
    assert caps.known is True
    assert Capabilities.from_dict(None, supports_tools=True).tools is True
    assert Capabilities.from_dict(None, supports_tools=False).tools is False


def test_model_info_derives_supports_tools_and_reads_old_documents():
    old = {
        "provider": "openrouter",
        "id": "vendor/old:free",
        "name": "Old",
        "context_length": 8192,
        "supports_tools": True,
        "expiration_date": "2026-11-30",
    }
    model = ModelInfo.from_dict(old)
    assert model.supports_tools is True
    assert model.capabilities.tools is True
    assert model.quota is None and model.tier == 1

    unknown = ModelInfo.from_dict({"provider": "groq", "id": "llama"})
    assert unknown.capabilities.to_dict()["source"] == "unknown"
    assert unknown.capabilities.tools is None
    assert unknown.supports_tools is False
    assert unknown.quota is None

    derived = ModelInfo("openrouter", "x", capabilities=Capabilities(tools=True, vision=True))
    assert derived.supports_tools is True
    assert derived.to_dict()["capabilities"]["vision"] is True


def test_quota_supports_five_hour_weekly_total_and_beta_periods():
    rolling = Quota.from_dict(
        {"unit": "tokens", "period": "5h", "limit": 120000, "remaining": 90000, "source": "api", "probesSinceRead": 4}
    )
    assert rolling.period == "rolling_5h" and rolling.window_seconds == 5 * 3600
    assert rolling.remaining_window == 89996 and rolling.remaining_today is None

    weekly = Quota(unit="tokens", period="weekly", limit=1200000, remaining=600000, source="api")
    assert weekly.period == "week" and weekly.window_seconds == 7 * 24 * 3600

    total = Quota(unit="tokens", period="total", limit=1000000, used=250000, source="manual")
    assert total.remaining_today is None
    assert total.remaining_total == 750000
    assert total.is_exhausted is False

    beta = Quota(unit="tokens", period="beta", source="none")
    assert beta.remaining_today is None and beta.remaining_total is None
    assert beta.is_exhausted is False


def test_quota_manual_values_are_not_reduced_by_local_probes():
    manual = Quota(unit="tokens", period="day", limit=100, remaining=100, source="manual", probes_since_read=9)
    assert manual.remaining_today == 100
    api = Quota(unit="requests", period="day", limit=50, used=5, remaining=10, source="api", probes_since_read=3)
    assert api.remaining_today == 7
    assert api.daily_free_limit == 50 and api.daily_free_remaining == 10


def test_quota_unknown_paths_and_legacy_quota_info():
    for raw in (None, {"unit": "widgets", "period": "fortnight", "limit": "many", "source": "magic"}):
        quota = Quota.from_dict(raw)
        assert quota.unit == "unknown" and quota.period == "unknown"
        assert quota.remaining_today is None and quota.remaining_total is None
        assert quota.is_exhausted is False

    legacy = QuotaInfo(daily_free_limit=50, daily_free_used=5, daily_free_remaining=45, probes_since_read=2)
    converted = legacy.to_quota()
    assert converted.unit == "requests" and converted.period == "day"
    assert converted.remaining_today == 43
    assert Quota.from_dict(legacy.to_dict()).remaining_today == 43
    # A snapshot may carry only the remaining counter.
    only_remaining = Quota.from_dict({"daily_free_remaining": 7})
    assert only_remaining.period == "day" and only_remaining.remaining_today == 7


def test_ranking_payload_is_schema_version_2_and_keeps_legacy_quota_fields():
    legacy = QuotaInfo(daily_free_limit=50, daily_free_used=5, daily_free_remaining=45)
    payload = _ranking_payload(["openrouter"], [], None, {"openrouter": legacy})
    assert payload["schema_version"] == RANKING_SCHEMA_VERSION == 2
    quota = payload["quota"]["openrouter"]
    # v1 readers keep seeing the old keys; v2 readers get the generic shape.
    assert quota["daily_free_limit"] == 50
    assert quota["unit"] == "requests" and quota["period"] == "day"
    assert quota["source"] == "api"
    assert quota["remaining_today"] == 45


def test_spec_exposes_the_shared_capability_and_quota_vocabulary():
    assert set(spec.CAPABILITY_FIELDS) == {"tools", "vision", "reasoning"}
    assert "unknown" in spec.CAPABILITY_SOURCES
    assert {"rolling_5h", "week", "total", "beta", "unknown"} <= set(spec.QUOTA_PERIODS)
    assert spec.QUOTA_PERIOD_SECONDS["rolling_5h"] == 18000
    assert spec.QUOTA_PERIOD_SECONDS["week"] == 604800
    assert "model" in spec.QUOTA_SCOPES
