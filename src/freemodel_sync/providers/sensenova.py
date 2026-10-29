"""SenseNova Token Plan provider (https://token.sensenova.cn, OpenAI-compatible).

Why the plan confirmation is required
-------------------------------------
SenseNova's Token Plan is a public beta with no public quota endpoint and no
per-request price the API promises to keep at zero. The catalogue does carry a
``pricing`` field (currently the string ``"0"`` for the beta models), but a
model can become paid at any time. This provider therefore lists and probes
nothing until you confirm the plan with ``providers.sensenova.plan:
token-plan``, the same pattern as Groq's ``plan: free``. Models whose
``pricing`` is not exactly the string ``"0"`` are dropped with a warning.

Models and quota
----------------
The model allowlist comes from ``providers.sensenova.models`` (default:
``deepseek-v4-flash`` and ``sensenova-6.8-flash-lite``). When
``GET /v1/models`` works, the allowlist is intersected with the catalogue;
when it does not, the configured allowlist is used unchanged. There is no
quota API; the generic quota is ``period="beta"`` with an unknown amount. An
optional ``free_until`` value is copied to ``expires_at`` for reminder UIs.

Errors
------
``spec/providers.json`` classifies 401/402 as account failures, 403 (a model
outside the plan) as a model failure, 429/408 and 5xx as transient, and other
codes as model failures.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional

import httpx

from ..models import Capabilities, ModelInfo, Quota, TestResult
from ..spec import classify_with, provider_spec
from .base import ProviderError, register_provider
from .openai_compat import OpenAICompatProvider, _as_int

logger = logging.getLogger(__name__)

_SPEC = provider_spec("sensenova")

#: used when ``providers.sensenova.models`` is not configured at all
DEFAULT_MODELS = ("deepseek-v4-flash", "sensenova-6.8-flash-lite")

_VISION_WORDS = ("image", "vision", "multimodal", "multi-modal", "图像", "视觉")
_TOOLS_WORDS = ("function", "tool", "工具")
_REASONING_WORDS = ("reasoning", "think", "推理")


def _pricing_is_zero(value: Any) -> bool:
    """Only the literal string ``"0"`` marks a free model (a number 0 does not)."""

    return isinstance(value, str) and value.strip() == "0"


def _feature_text(value: Any) -> str:
    """Flatten a catalogue capability field (strings, lists or objects) to lower-case text."""

    if isinstance(value, str):
        return value.lower()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    except (TypeError, ValueError):
        return str(value).lower()


def _capabilities_from_catalog(raw: Any) -> Capabilities:
    """Infer capability flags from ``supported_features`` and ``businesses``.

    A flag is set only when a matching feature is present; absence stays
    unknown rather than false, because the two fields are not documented as a
    complete capability list.
    """

    if not isinstance(raw, dict):
        return Capabilities(source="unknown")
    text = _feature_text(raw.get("supported_features")) + " " + _feature_text(raw.get("businesses"))
    tools = any(word in text for word in _TOOLS_WORDS)
    vision = any(word in text for word in _VISION_WORDS)
    reasoning = any(word in text for word in _REASONING_WORDS)
    return Capabilities(
        tools=tools or None,
        vision=vision or None,
        reasoning=reasoning or None,
        source="catalog" if (tools or vision or reasoning) else "unknown",
    )


def _strings(value: Any) -> List[str]:
    """Read a configured model list from a list, tuple, set or comma/space string."""

    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.replace(",", " ").split() if part]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


@register_provider
class SenseNovaProvider(OpenAICompatProvider):
    """SenseNova Token Plan models, usable only inside the beta."""

    name = "sensenova"
    base_url = _SPEC["baseURL"]
    api_key_env = _SPEC["apiKeyEnv"]
    max_tokens_param = _SPEC["probe"]["maxTokensParam"]
    auth_kind = _SPEC["authKind"]
    tier = _SPEC["tier"]

    @staticmethod
    def _classify(status_code: Optional[int], error_obj: Dict[str, Any]) -> str:
        # providers.sensenova.errorMap: 401/402 account, 403 model (outside the
        # plan), 408/429/5xx transient, other codes model.
        return classify_with(_SPEC["errorMap"], status_code, error_obj)

    def _check_plan(self) -> None:
        plan = str(self.options.get("plan") or "").strip().lower().replace("_", "-").replace(" ", "-")
        expected = str(_SPEC["freeRule"]["value"])
        if plan != expected:
            logger.warning("SenseNova: plan is not confirmed; nothing will be listed or probed")
            raise ProviderError(
                "sensenova: set providers.sensenova.plan: token-plan to confirm you are in the "
                "SenseNova Token Plan public beta. The API does not report a quota and prices can "
                "change, so nothing is listed or probed without this confirmation."
            )

    def _allowed_models(self) -> Optional[List[str]]:
        """Configured allowlist, or ``None`` to use every catalogue model priced ``"0"``.

        An absent option means the default list; an explicitly empty list means
        "use the catalogue" (the plugin uses the same convention).
        """

        if "models" not in self.options:
            return list(DEFAULT_MODELS)
        configured = _strings(self.options.get("models"))
        if not configured:
            return None
        seen: Dict[str, None] = {}
        for model_id in configured:
            seen.setdefault(model_id, None)
        return list(seen)

    def _catalog(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """GET /models as ``{id: model}``, or ``None`` when the catalogue is unavailable."""

        try:
            response = self._get_client().get(f"{self.base_url}/models", headers=self._auth_headers())
            if response.status_code != 200:
                logger.warning(
                    "SenseNova model list failed: HTTP %s; using the configured model allowlist",
                    response.status_code,
                )
                return None
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("SenseNova model list failed (%s); using the configured model allowlist", type(exc).__name__)
            return None
        except ValueError:
            logger.warning("SenseNova returned invalid JSON; using the configured model allowlist")
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            logger.warning("SenseNova returned an unexpected models payload; using the configured model allowlist")
            return None
        catalog: Dict[str, Dict[str, Any]] = {}
        for raw in payload["data"]:
            if isinstance(raw, dict):
                model_id = raw.get("id")
                if isinstance(model_id, str) and model_id:
                    catalog[model_id] = raw
        return catalog

    def _model(self, raw: Optional[Dict[str, Any]], fallback_id: str) -> ModelInfo:
        data: Dict[str, Any] = raw or {}
        model_id = str(data.get("id") or fallback_id)
        capabilities = _capabilities_from_catalog(data)
        context = _as_int(data.get("context_length")) or _as_int(data.get("context_window")) or 0
        return ModelInfo(
            provider=self.name,
            id=model_id,
            name=str(data.get("name") or model_id),
            context_length=context,
            supports_tools=capabilities.tools is True,
            capabilities=capabilities,
            raw=data,
            tier=self.tier,
        )

    def capabilities_for(self, model: ModelInfo) -> Capabilities:
        return _capabilities_from_catalog(model.raw)

    def discover(self) -> List[ModelInfo]:
        self._check_plan()
        if not self.api_key:
            raise ProviderError(f"sensenova: listing models needs {self.api_key_env} (the model list requires a key)")

        allowed = self._allowed_models()
        catalog = self._catalog()
        if catalog is None:
            # The catalogue is supplementary: without it, the confirmed
            # allowlist is still usable (metadata such as context is unknown).
            return [self._model(None, model_id) for model_id in (allowed or [])]

        models: List[ModelInfo] = []
        if allowed is None:
            candidates = list(catalog.values())
        else:
            candidates = [catalog[model_id] for model_id in allowed if model_id in catalog]
        for raw in candidates:
            model_id = str(raw.get("id") or "")
            if not model_id:
                continue
            if not _pricing_is_zero(raw.get("pricing")):
                logger.warning(
                    'skipping SenseNova model %s: pricing is %r, not the string "0" (it is no longer free)',
                    model_id,
                    raw.get("pricing"),
                )
                continue
            models.append(self._model(raw, model_id))
        return models

    def quota(self) -> Quota:
        """The public beta has no quota API; only an optional user-supplied end date."""

        free_until = self.options.get("free_until")
        expires_at = str(free_until).strip() if free_until is not None else ""
        return Quota(period="beta", unit="unknown", source="none", expires_at=expires_at or None)

    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        self._check_plan()
        return super().test(model, timeout=timeout)
