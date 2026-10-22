"""Filter, score and rank free models based on probe results.

The ranking is intentionally simple and explainable: availability dominates,
then latency, context window, tool support, with penalties for models that are
about to expire or have not been tested yet.
"""

from __future__ import annotations

import fnmatch
import math
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional, Sequence, Tuple

from .models import ModelInfo, RankedModel, Selection, TestResult

_LOG2_MILLION = math.log2(1_000_000)


@dataclass
class RankWeights:
    """Weights for the individual ranking signals."""

    availability: float = 100.0
    latency: float = 30.0
    context: float = 20.0
    tools: float = 15.0
    expiry_penalty: float = 50.0
    untested_penalty: float = 40.0


#: id/name globs (case-insensitive) of free models that are not chat models:
#: safety classifiers, moderation, embedding, reranking and speech models.
NON_CHAT_PATTERNS = (
    "*content-safety*",
    "*safeguard*",
    "*guard*",
    "*moderation*",
    "*classifier*",
    "*embed*",
    "*rerank*",
    "*whisper*",
    "*transcrib*",
    "*-tts*",
    "*orpheus*",
    "*playai-tts*",
)


def is_non_chat(model: ModelInfo) -> bool:
    """True if *model* looks like a classifier/embedding/speech model, not a chat model."""

    haystacks = (model.id.lower(), (model.name or "").lower())
    return any(fnmatch.fnmatchcase(h, pattern) for h in haystacks for pattern in NON_CHAT_PATTERNS)


def _matches_any(model_id: str, patterns: Optional[Sequence[str]]) -> bool:
    if not patterns:
        return False
    return any(fnmatch.fnmatchcase(model_id, pattern) for pattern in patterns)


def filter_models(
    models: Iterable[ModelInfo],
    *,
    require_tools: bool = False,
    min_context: int = 0,
    exclude_expiring_within_days: Optional[int] = None,
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    today: Optional[date] = None,
    exclude_non_chat: bool = True,
) -> List[ModelInfo]:
    """Return models passing the configured filters, preserving input order.

    ``exclude_non_chat`` drops models matching :data:`NON_CHAT_PATTERNS`
    (safety classifiers, embedding, rerank, speech) unless they are matched
    explicitly by ``include``.
    """

    kept: List[ModelInfo] = []
    for model in models:
        if exclude_non_chat and is_non_chat(model) and not _matches_any(model.id, include):
            continue
        if require_tools and not model.supports_tools:
            continue
        if model.context_length < min_context:
            continue
        if exclude_expiring_within_days is not None:
            days = model.days_until_expiry(today)
            if days is not None and days <= exclude_expiring_within_days:
                continue
        if include and not _matches_any(model.id, include):
            continue
        if exclude and _matches_any(model.id, exclude):
            continue
        kept.append(model)
    return kept


def score_model(
    model: ModelInfo,
    test: Optional[TestResult],
    weights: RankWeights,
    today: Optional[date] = None,
) -> Tuple[float, List[str]]:
    """Compute a model's score and a short list of human-readable reasons."""

    reasons: List[str] = []

    if test is not None and not test.ok:
        return -1000.0, [f"failed: {test.error or 'unknown error'}"]

    if test is None:
        score = -weights.untested_penalty
        reasons.append("untested")
    else:
        score = weights.availability

    if test is not None and test.ok and test.ttft_ms:
        score += weights.latency * max(0.0, 1.0 - test.ttft_ms / 10000.0)

    context_length = max(model.context_length, 1)
    score += weights.context * min(1.0, math.log2(context_length) / _LOG2_MILLION)

    if model.supports_tools:
        score += weights.tools

    days = model.days_until_expiry(today)
    if days is not None and days < 30:
        score -= weights.expiry_penalty * (30 - max(days, 0)) / 30.0
        reasons.append(f"expires in {days} days")

    return score, reasons


def rank(
    models: Iterable[ModelInfo],
    results: dict,
    weights: Optional[RankWeights] = None,
    today: Optional[date] = None,
) -> List[RankedModel]:
    """Score and sort models by descending score, breaking ties by model id."""

    weights = weights or RankWeights()
    ranked: List[RankedModel] = []
    for model in models:
        test = results.get(model.key)
        score, reasons = score_model(model, test, weights, today=today)
        ranked.append(RankedModel(model=model, score=score, test=test, reasons=reasons))
    ranked.sort(key=lambda item: (-item.score, item.model.id))
    return ranked


def select(
    ranked: Sequence[RankedModel],
    fallback_count: int = 3,
    *,
    allow_untested: bool = False,
) -> Optional[Selection]:
    """Pick the best usable model plus fallbacks.

    Returns ``None`` when no tested-and-working model exists.  Fallbacks are the
    next working models *of the primary's provider*: a target config has
    one base URL and one key, so a fallback from another provider could not
    be used.  Only when ``allow_untested`` is true are remaining
    slots filled with untested models (callers should flag them); failed models
    are never selected.
    """

    primary: Optional[RankedModel] = None
    for item in ranked:
        if item.test is not None and item.test.ok:
            primary = item
            break
    if primary is None:
        return None

    limit = max(0, int(fallback_count))
    fallbacks: List[RankedModel] = []
    chosen = {id(primary)}

    ranked = [item for item in ranked if item.model.provider == primary.model.provider]
    for item in ranked:
        if len(fallbacks) >= limit:
            break
        if id(item) in chosen:
            continue
        if item.test is not None and item.test.ok:
            fallbacks.append(item)
            chosen.add(id(item))

    if allow_untested and len(fallbacks) < limit:
        for item in ranked:
            if len(fallbacks) >= limit:
                break
            if id(item) in chosen:
                continue
            if item.test is None:
                fallbacks.append(item)
                chosen.add(id(item))

    return Selection(primary=primary, fallbacks=fallbacks)
