"""Provider plugin interface.

A provider knows how to (1) list its free models, (2) probe one model with a
tiny request, and optionally (3) report quota. New providers (SiliconFlow,
Zhipu Flash, Groq, Gemini, ...) subclass :class:`Provider` and register
themselves with :func:`register_provider`.
"""

from __future__ import annotations

import abc
from typing import Callable, Dict, List, Optional, Type

from ..models import ModelInfo, QuotaInfo, TestResult


class ProviderError(RuntimeError):
    """Raised when a provider catalogue or API cannot be used."""


class Provider(abc.ABC):
    #: short identifier used in config files and model keys
    name: str = ""
    #: OpenAI-compatible base URL that tools should use for this provider
    base_url: str = ""
    #: environment variable that holds the user's API key
    api_key_env: str = ""

    def __init__(self, api_key: Optional[str] = None, **options: object) -> None:
        self.api_key = api_key
        self.options = options

    @abc.abstractmethod
    def discover(self) -> List[ModelInfo]:
        """Return the provider's currently free models (no key required if possible)."""

    @abc.abstractmethod
    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        """Send one tiny streaming request and measure availability / time-to-first-token."""

    def quota(self) -> Optional[QuotaInfo]:
        """Return quota information, or ``None`` if the provider cannot report it."""
        return None


_REGISTRY: Dict[str, Type[Provider]] = {}


def register_provider(cls: Type[Provider]) -> Type[Provider]:
    if not cls.name:
        raise ValueError("provider class must define a non-empty 'name'")
    _REGISTRY[cls.name] = cls
    return cls


def get_provider_class(name: str) -> Type[Provider]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ProviderError(
            f"unknown provider {name!r}; available: {', '.join(sorted(_REGISTRY)) or 'none'}"
        ) from None


def available_providers() -> List[str]:
    return sorted(_REGISTRY)


ProviderFactory = Callable[..., Provider]
