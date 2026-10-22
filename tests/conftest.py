from __future__ import annotations

import json
from pathlib import Path

import pytest

from freemodel_sync.models import ModelInfo, RankedModel, Selection, TestResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def models_payload():
    return json.loads((FIXTURES / "openrouter_models.json").read_text(encoding="utf-8"))


def make_selection(primary="vendor/a:free", fallbacks=("vendor/b:free", "vendor/c:free"), provider="openrouter"):
    def rm(mid):
        return RankedModel(
            ModelInfo(provider, mid),
            100.0,
            TestResult(key=f"{provider}|{mid}", ok=True, ttft_ms=100.0),
        )

    return Selection(primary=rm(primary), fallbacks=[rm(f) for f in fallbacks])


@pytest.fixture
def selection():
    return make_selection()
