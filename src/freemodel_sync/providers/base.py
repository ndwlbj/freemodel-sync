"""Provider plugin interface.

A provider knows how to (1) list its free models, (2) probe one model with a
tiny request, and optionally (3) report quota. New providers (SiliconFlow,
Zhipu Flash, Groq, Gemini, ...) subclass :class:`Provider` and register
themselves with :func:`register_provider`.
"""

from __future__ import annotations

import abc
from typing import Callable, Dict, List, Optional, Type, Union

from ..models import Capabilities, ModelInfo, Quota, QuotaInfo, TestResult


class ProviderError(RuntimeError):
    """Raised when a provider catalogue or API cannot be used."""


class Provider(abc.ABC):
    #: short identifier used in config files and model keys
    name: str = ""
    #: OpenAI-compatible base URL that tools should use for this provider
    base_url: str = ""
    #: environment variable that holds the user's API key
    api_key_env: str = ""
    #: how the provider authenticates (``api_key``, ``none``, ...)
    auth_kind: str = "api_key"
    #: 1 = official public API, 2 = manually registered platform
    tier: int = 1

    def __init__(self, api_key: Optional[str] = None, **options: object) -> None:
        self.api_key = api_key
        self.options = options

    @abc.abstractmethod
    def discover(self) -> List[ModelInfo]:
        """Return the provider's currently free models (no key required if possible)."""

    @abc.abstractmethod
    def test(self, model: ModelInfo, timeout: float = 30.0) -> TestResult:
        """Send one tiny streaming request and measure availability / time-to-first-token."""

    def capabilities_for(self, model: ModelInfo) -> Capabilities:
        """Return what a model can do, or unknown when the provider cannot tell.

        Providers whose catalogue carries capability fields can override this
        (SenseNova and Bailian do); the default is deliberately unknown rather
        than a false negative.
        """

        return Capabilities(source="unknown")

    def quota(self) -> Optional[Union[QuotaInfo, Quota]]:
        """Return quota information, or ``None`` if the provider cannot report it.

        Providers may return the legacy :class:`QuotaInfo` (daily request
        counters) or the generic :class:`Quota` (rolling/weekly/total/beta
        windows). The CLI normalises either form to :class:`Quota`.
        """
        return None

    def close(self) -> None:  # noqa: B027 - optional hook, a no-op by default
        """Release network resources (e.g. an HTTP client the provider created).

        Safe to call more than once; the provider can still be used afterwards
        (it creates a new client on demand).
        """

    def __enter__(self) -> Provider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


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
        raise ProviderError(f"unknown provider {name!r}; available: {', '.join(sorted(_REGISTRY)) or 'none'}") from None


def available_providers() -> List[str]:
    return sorted(_REGISTRY)


ProviderFactory = Callable[..., Provider]
