"""Load and validate the YAML configuration file.

Every section is optional; missing values fall back to the defaults documented
in :data:`DEFAULT_CONFIG`.  Paths are expanded with :func:`os.path.expanduser`
so ``~`` works in config files.

Example::

    providers:
      openrouter:
        enabled: true
        api_key_env: OPENROUTER_API_KEY
    filters:
      require_tools: false
      min_context: 0
      exclude_expiring_within_days: 3
    testing:
      max_tests: 5
      cache_ttl_hours: 6
      transient_ttl_minutes: 30
      daily_free_limit: null   # override the provider-reported free requests/day
      cache_path: ~/.cache/freemodel-sync/results.json
    ranking:
      weights:
        availability: 100
      fallback_count: 3
    state_path: ~/.local/state/freemodel-sync/state.json
    targets:
      - adapter: dsh
        path: ~/.config/dsh/cordis.patch.yml
        options: {}
    notify:
      telegram: null
      webhook: null
"""

from __future__ import annotations

import copy
import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml

from .flags import parse_bool
from .models import AuthKind, Quota
from .ranking import RankWeights
from .spec import ranking_spec

LOG = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "~/.config/freemodel-sync/config.yml"
DEFAULT_CACHE_PATH = "~/.cache/freemodel-sync/results.json"
DEFAULT_STATE_PATH = "~/.local/state/freemodel-sync/state.json"

#: authentication kinds a manual registration may declare
AUTH_KINDS: tuple[AuthKind, ...] = ("none", "api_key", "pat", "oauth_manual")

#: Defaults for every supported config key.  ``load_config`` deep-merges the
#: user's file onto a copy of this mapping.
DEFAULT_CONFIG: Dict[str, Any] = {
    "providers": {
        "openrouter": {
            "enabled": True,
            "api_key_env": "OPENROUTER_API_KEY",
        }
    },
    "filters": {
        "require_tools": False,
        "min_context": 0,
        "exclude_expiring_within_days": 3,
        "include": [],
        "exclude": [],
        "exclude_non_chat": True,
        "include_manual": False,
    },
    "testing": {
        "max_tests": 5,
        "cache_ttl_hours": 6,
        "transient_ttl_minutes": 30,
        "timeout_s": 30,
        "reserve_requests": 10,
        "daily_free_limit": None,
        "cache_path": DEFAULT_CACHE_PATH,
    },
    "ranking": {
        "weights": {
            "availability": 100.0,
            "latency": 30.0,
            "context": 20.0,
            "tools": 15.0,
            "expiry_penalty": 50.0,
            "untested_penalty": 40.0,
            "capacity_penalty": 50.0,
        },
        "fallback_count": 3,
        "fallbacks_allow_untested": False,
        "capacity_downgrade_after": int(ranking_spec()["capacity"]["downgradeAfter"]),
    },
    "output": {"ranking_json": None},
    "backups": {"keep": 5, "dir": None},
    "state_path": DEFAULT_STATE_PATH,
    "manual_providers": {},
    "targets": [],
    "notify": {"telegram": None, "webhook": None},
}


class ConfigError(ValueError):
    """Raised when the config file is unreadable or has an invalid value."""


class _Section(Mapping):
    """Read-only mapping view over a config dataclass' fields.

    This keeps attribute access (``cfg.filters.min_context``) and dict-style
    access (``cfg.filters["min_context"]``) equally usable.
    """

    def __getitem__(self, key: str) -> Any:
        if key in self.__dataclass_fields__:  # type: ignore[attr-defined]
            return getattr(self, key)
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.__dataclass_fields__)  # type: ignore[attr-defined]

    def __len__(self) -> int:
        return len(self.__dataclass_fields__)  # type: ignore[attr-defined]


@dataclass
class ProviderConfig(_Section):
    """Settings for one provider (keyed by provider name in ``providers``)."""

    enabled: bool = True
    api_key_env: str = ""
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.options, dict):
            self.options = dict(self.options)

    def to_dict(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, "api_key_env": self.api_key_env, **self.options}


@dataclass
class ManualModelConfig(_Section):
    """One model of a manually registered, tier-2 platform.

    Only public facts live here: a model id, optional label, capability hint,
    hand-entered quota and expiry date. There is deliberately no credential
    field; the login belongs to the platform's dsh plugin.
    """

    id: str
    name: str = ""
    tools: Optional[bool] = None
    quota: Optional[Quota] = None
    expires_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.quota, Mapping):
            self.quota = Quota.from_dict(self.quota)
        if self.quota is not None:
            self.quota.source = "manual"
            if self.quota.expires_at is None and self.expires_at is not None:
                self.quota.expires_at = self.expires_at
        if self.expires_at is not None:
            self.expires_at = _require_date(self.expires_at, f"manual model {self.id}.expires_at")

    @property
    def expiration_date(self) -> Optional[date]:
        return date.fromisoformat(self.expires_at) if self.expires_at else None

    def expired(self, today: Optional[date] = None) -> bool:
        expiry = self.expiration_date
        return expiry is not None and expiry < (today or date.today())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tools": self.tools,
            "quota": self.quota.to_dict() if self.quota is not None else None,
            "expires_at": self.expires_at,
            "expired": self.expired(),
        }


@dataclass
class ManualProviderConfig(_Section):
    """A manually registered platform (ZCode / Qoder / WorkBuddy, ...)."""

    name: str
    display_name: str = ""
    auth: str = "oauth_manual"
    dsh_provider: str = ""
    dsh_plugin: str = ""
    models: List[ManualModelConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.display_name = self.display_name or self.name
        self.dsh_provider = self.dsh_provider or self.name
        self.models = [
            model if isinstance(model, ManualModelConfig) else ManualModelConfig(**dict(model)) for model in self.models
        ]

    def expired(self, today: Optional[date] = None) -> bool:
        """True when every registered model has expired (nothing can be discovered)."""

        return bool(self.models) and all(model.expired(today) for model in self.models)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "auth": self.auth,
            "dsh_provider": self.dsh_provider,
            "dsh_plugin": self.dsh_plugin,
            "expired": self.expired(),
            "models": [model.to_dict() for model in self.models],
        }


@dataclass
class FilterConfig(_Section):
    require_tools: bool = False
    min_context: int = 0
    exclude_expiring_within_days: Optional[int] = 3
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    #: drop safety classifiers, embedding/rerank and speech models (ranking.NON_CHAT_PATTERNS)
    exclude_non_chat: bool = True
    #: include tier-2 manual registrations in discovery/ranking (off by default)
    include_manual: bool = False


@dataclass
class TestingConfig(_Section):
    max_tests: int = 5
    cache_ttl_hours: float = 6
    #: cache lifetime for transient model failures (upstream 429, 5xx, timeouts)
    transient_ttl_minutes: float = 30
    timeout_s: float = 30
    reserve_requests: int = 10
    #: overrides the provider-reported daily free request limit (e.g. 50 or 1000)
    daily_free_limit: Optional[int] = None
    cache_path: Path = field(default_factory=lambda: _expand_path(DEFAULT_CACHE_PATH))

    def __post_init__(self) -> None:
        self.cache_path = _expand_path(self.cache_path)

    @property
    def cache_ttl_s(self) -> float:
        """Cache TTL in seconds (convenience for :func:`tester.run_tests`)."""

        return float(self.cache_ttl_hours) * 3600.0

    @property
    def transient_ttl_s(self) -> float:
        return float(self.transient_ttl_minutes) * 60.0


@dataclass
class RankingConfig(_Section):
    weights: RankWeights = field(default_factory=RankWeights)
    fallback_count: int = 3
    #: fill empty fallback slots with models that were never probed
    fallbacks_allow_untested: bool = False
    #: consecutive capacity failures after which a model is no longer selectable
    capacity_downgrade_after: int = field(default_factory=lambda: int(ranking_spec()["capacity"]["downgradeAfter"]))


@dataclass
class OutputConfig(_Section):
    ranking_json: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.ranking_json is not None:
            self.ranking_json = _expand_path(self.ranking_json)


@dataclass
class TargetConfig(_Section):
    """One adapter target: which adapter to use, where its file lives, options."""

    adapter: str
    path: Path
    options: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path = _expand_path(self.path)
        if not isinstance(self.options, dict):
            self.options = dict(self.options)


@dataclass
class BackupConfig(_Section):
    """How many backups to keep per target and where to put them."""

    keep: int = 5
    dir: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.dir is not None:
            self.dir = _expand_path(self.dir)


@dataclass
class NotifyConfig(_Section):
    telegram: Optional[Dict[str, Any]] = None
    webhook: Optional[Dict[str, Any]] = None


@dataclass
class Config(_Section):
    """Fully resolved configuration (defaults + user file)."""

    providers: Dict[str, ProviderConfig] = field(
        default_factory=lambda: {"openrouter": ProviderConfig(enabled=True, api_key_env="OPENROUTER_API_KEY")}
    )
    #: Tier-2 manual registrations, keyed by provider name. Never hold a credential.
    manual_providers: Dict[str, ManualProviderConfig] = field(default_factory=dict)
    filters: FilterConfig = field(default_factory=FilterConfig)
    testing: TestingConfig = field(default_factory=TestingConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    backups: BackupConfig = field(default_factory=BackupConfig)
    state_path: Path = field(default_factory=lambda: _expand_path(DEFAULT_STATE_PATH))
    targets: List[TargetConfig] = field(default_factory=list)
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    def __post_init__(self) -> None:
        self.providers = {
            str(name): value if isinstance(value, ProviderConfig) else ProviderConfig(**dict(value))
            for name, value in self.providers.items()
        }
        self.manual_providers = {
            str(name): value
            if isinstance(value, ManualProviderConfig)
            else ManualProviderConfig(name=str(name), **dict(value))
            for name, value in self.manual_providers.items()
        }
        if not isinstance(self.filters, FilterConfig):
            self.filters = FilterConfig(**dict(self.filters))
        if not isinstance(self.testing, TestingConfig):
            self.testing = TestingConfig(**dict(self.testing))
        if not isinstance(self.ranking, RankingConfig):
            weights = self.ranking.get("weights") if isinstance(self.ranking, Mapping) else None
            if isinstance(weights, Mapping):
                weights = RankWeights(**dict(weights))
            self.ranking = RankingConfig(
                weights=weights or RankWeights(),
                fallback_count=int(dict(self.ranking).get("fallback_count", 3)),
                fallbacks_allow_untested=bool(dict(self.ranking).get("fallbacks_allow_untested", False)),
                capacity_downgrade_after=int(dict(self.ranking).get("capacity_downgrade_after", 3)),
            )
        if not isinstance(self.output, OutputConfig):
            self.output = OutputConfig(**dict(self.output))
        if not isinstance(self.backups, BackupConfig):
            self.backups = BackupConfig(**dict(self.backups))
        if not isinstance(self.notify, NotifyConfig):
            self.notify = NotifyConfig(**dict(self.notify))
        self.state_path = _expand_path(self.state_path)
        self.targets = [
            target if isinstance(target, TargetConfig) else TargetConfig(**dict(target)) for target in self.targets
        ]

    def enabled_providers(self) -> List[str]:
        """Return the names of providers that are enabled, in config order."""

        return [name for name, cfg in self.providers.items() if cfg.enabled]


def _expand_path(value: Union[str, os.PathLike]) -> Path:
    return Path(os.path.expanduser(str(value)))


def _default_path() -> Path:
    env = os.environ.get("FREEMODEL_SYNC_CONFIG")
    return _expand_path(env or DEFAULT_CONFIG_PATH)


def _deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""

    merged = copy.deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _require_mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value


def _require_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{where} must be a boolean, got {type(value).__name__}")
    return value


def _require_int(value: Any, where: str, *, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} must be an integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{where} must be >= {minimum}, got {value}")
    return value


def _require_number(value: Any, where: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where} must be a number, got {type(value).__name__}")
    number = float(value)
    if positive and number <= 0:
        raise ConfigError(f"{where} must be > 0, got {value}")
    return number


def _require_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where} must be a non-empty string")
    return value


def _optional_str_list(value: Any, where: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where} must be a list of strings")
    return list(value)


def _require_date(value: Any, where: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ConfigError(f"{where} must be a YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{where} is not a valid date: {exc}") from None
    return value


#: Keys that would hold a credential (compared with ``_``/``-`` removed, lower-case).
_FORBIDDEN_KEYS = frozenset(
    {
        "token",
        "pat",
        "cookie",
        "password",
        "secret",
        "key",
        "apikey",
        "apikeyenv",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
    }
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: A string that looks like a real key rather than a placeholder (``sk-...`` etc.).
_KEY_LIKE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(?:sk-|gsk_|pat_|ghp_|xox[abp]-)[A-Za-z0-9._-]{12,}|(?i:bearer\s+[A-Za-z0-9._-]{20,})"
)


def _normalise_key(name: Any) -> str:
    return re.sub(r"[_-]", "", str(name)).lower()


def _looks_like_key(value: str) -> bool:
    return _KEY_LIKE_RE.search(value) is not None


def check_secret_free(value: Any, where: str, *, allow_api_key_env: bool = False) -> None:
    """Reject credential-shaped keys and values anywhere under *value*.

    Used for ``manual_providers`` and every ``providers.*`` section. The only
    permitted exception is the ``api_key_env`` key, whose value must be an
    environment-variable *name* (never a key).
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if _normalise_key(key_text) in _FORBIDDEN_KEYS:
                if not (allow_api_key_env and key_text == "api_key_env"):
                    raise ConfigError(
                        f"{where}.{key_text}: credential-bearing keys are not allowed in the config; "
                        "store the value in an environment variable and write only the variable name "
                        "(api_key_env for a tier-1 provider; tier-2 platforms keep their login in their dsh plugin)"
                    )
            if key_text == "api_key_env":
                if not isinstance(item, str) or not _ENV_NAME_RE.fullmatch(item):
                    raise ConfigError(f"{where}.api_key_env must be an environment variable name, not a key")
                continue
            check_secret_free(item, f"{where}.{key_text}", allow_api_key_env=allow_api_key_env)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            check_secret_free(item, f"{where}[{index}]", allow_api_key_env=allow_api_key_env)
    elif isinstance(value, str) and _looks_like_key(value):
        raise ConfigError(
            f"{where}: value looks like an API key or token; store it in an environment variable / the dsh "
            "credential store instead, never in the config file"
        )


_QUOTA_KEYS = frozenset({"unit", "period", "limit", "used", "remaining", "resets_at", "expires_at", "source", "scope"})


def _parse_manual_model(raw: Any, where: str) -> ManualModelConfig:
    section = _require_mapping(raw, where)
    check_secret_free(section, where)
    unknown = set(section) - {"id", "name", "tools", "quota", "expires_at"}
    if unknown:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(sorted(str(key) for key in unknown))}")
    model_id = _require_str(section.get("id"), f"{where}.id")
    name = section.get("name", "")
    if name is None:
        name = ""
    if not isinstance(name, str):
        raise ConfigError(f"{where}.name must be a string")
    tools = section.get("tools")
    if tools is not None and not isinstance(tools, bool):
        raise ConfigError(f"{where}.tools must be a boolean")
    quota: Optional[Quota] = None
    if section.get("quota") is not None:
        quota_raw = _require_mapping(section["quota"], f"{where}.quota")
        check_secret_free(quota_raw, f"{where}.quota")
        unknown_quota = set(quota_raw) - _QUOTA_KEYS
        if unknown_quota:
            raise ConfigError(f"{where}.quota: unknown key(s): {', '.join(sorted(str(key) for key in unknown_quota))}")
        quota = Quota.from_dict(quota_raw)
        quota.source = "manual"
    expires_at = section.get("expires_at")
    if expires_at is not None:
        expires_at = _require_date(expires_at, f"{where}.expires_at")
    return ManualModelConfig(id=model_id, name=name, tools=tools, quota=quota, expires_at=expires_at)


def _parse_manual_providers(raw: Any, known_providers: Mapping[str, Any]) -> Dict[str, ManualProviderConfig]:
    if raw is None:
        return {}
    mapping = _require_mapping(raw, "manual_providers")
    entries: Dict[str, ManualProviderConfig] = {}
    for name, value in mapping.items():
        provider_name = str(name)
        where = f"manual_providers.{provider_name}"
        if not re.fullmatch(r"[a-z][a-z0-9-]*", provider_name):
            raise ConfigError(f"{where}: name must match [a-z][a-z0-9-]*")
        if provider_name in known_providers:
            raise ConfigError(f"{where}: conflicts with the tier-1 provider {provider_name!r}; choose another name")
        section = _require_mapping(value if value is not None else {}, where)
        check_secret_free(section, where)
        unknown = set(section) - {"display_name", "auth", "dsh_provider", "dsh_plugin", "models"}
        if unknown:
            raise ConfigError(f"{where}: unknown key(s): {', '.join(sorted(str(key) for key in unknown))}")
        display_name = section.get("display_name", provider_name)
        if not isinstance(display_name, str):
            raise ConfigError(f"{where}.display_name must be a string")
        auth = section.get("auth", "oauth_manual")
        if auth not in AUTH_KINDS:
            raise ConfigError(f"{where}.auth must be one of: {', '.join(AUTH_KINDS)}")
        dsh_provider = section.get("dsh_provider", provider_name)
        if dsh_provider is None:
            dsh_provider = ""
        if not isinstance(dsh_provider, str):
            raise ConfigError(f"{where}.dsh_provider must be a string")
        dsh_plugin = section.get("dsh_plugin", "")
        if dsh_plugin is None:
            dsh_plugin = ""
        if not isinstance(dsh_plugin, str):
            raise ConfigError(f"{where}.dsh_plugin must be a string")
        models_raw = section.get("models")
        if not isinstance(models_raw, list) or not models_raw:
            raise ConfigError(f"{where}.models must be a non-empty list")
        models = [_parse_manual_model(item, f"{where}.models[{index}]") for index, item in enumerate(models_raw)]
        ids = [model.id for model in models]
        duplicates = sorted({model_id for model_id in ids if ids.count(model_id) > 1})
        if duplicates:
            raise ConfigError(f"{where}.models: duplicate model id(s): {', '.join(duplicates)}")
        entries[provider_name] = ManualProviderConfig(
            name=provider_name,
            display_name=display_name,
            auth=str(auth),
            dsh_provider=dsh_provider,
            dsh_plugin=dsh_plugin,
            models=models,
        )
    return entries


def _parse_providers(raw: Any) -> Dict[str, ProviderConfig]:
    mapping = _require_mapping(raw, "providers")
    from .providers import available_providers, get_provider_class

    known = set(available_providers())
    providers: Dict[str, ProviderConfig] = {}
    for name, value in mapping.items():
        where = f"providers.{name}"
        if str(name) not in known:
            raise ConfigError(f"{where}: unknown provider {name!r}; available: {', '.join(sorted(known))}")
        section = _require_mapping(value if value is not None else {}, where)
        check_secret_free(section, where, allow_api_key_env=True)
        enabled = _require_bool(section.get("enabled", True), f"{where}.enabled")
        # Default to the provider's own variable: never send one provider's key to another.
        api_key_env = section.get("api_key_env", get_provider_class(str(name)).api_key_env)
        if api_key_env is None:
            api_key_env = ""
        elif not isinstance(api_key_env, str):
            raise ConfigError(f"{where}.api_key_env must be a string or null")
        extra = {key: item for key, item in section.items() if key not in {"enabled", "api_key_env"}}
        providers[str(name)] = ProviderConfig(enabled=enabled, api_key_env=api_key_env, options=extra)
    return providers


def _parse_filters(raw: Any) -> FilterConfig:
    section = _require_mapping(raw, "filters")
    min_context = _require_int(section.get("min_context", 0), "filters.min_context", minimum=0)
    expiring = section.get("exclude_expiring_within_days", 3)
    if expiring is not None:
        expiring = _require_int(expiring, "filters.exclude_expiring_within_days", minimum=0)
    return FilterConfig(
        require_tools=_require_bool(section.get("require_tools", False), "filters.require_tools"),
        min_context=min_context,
        exclude_expiring_within_days=expiring,
        include=_optional_str_list(section.get("include", []), "filters.include"),
        exclude=_optional_str_list(section.get("exclude", []), "filters.exclude"),
        exclude_non_chat=_require_bool(section.get("exclude_non_chat", True), "filters.exclude_non_chat"),
        include_manual=_require_bool(section.get("include_manual", False), "filters.include_manual"),
    )


def _parse_testing(raw: Any) -> TestingConfig:
    section = _require_mapping(raw, "testing")
    cache_path = section.get("cache_path", DEFAULT_CACHE_PATH)
    cache_path = _require_str(cache_path, "testing.cache_path")
    return TestingConfig(
        # 0 would probe nothing yet report success: at least one probe per run.
        max_tests=_require_int(section.get("max_tests", 5), "testing.max_tests", minimum=1),
        cache_ttl_hours=_require_number(section.get("cache_ttl_hours", 6), "testing.cache_ttl_hours", positive=True),
        transient_ttl_minutes=_require_number(
            section.get("transient_ttl_minutes", 30), "testing.transient_ttl_minutes", positive=True
        ),
        timeout_s=_require_number(section.get("timeout_s", 30), "testing.timeout_s", positive=True),
        reserve_requests=_require_int(section.get("reserve_requests", 10), "testing.reserve_requests", minimum=0),
        daily_free_limit=(
            None
            if section.get("daily_free_limit") is None
            else _require_int(section.get("daily_free_limit"), "testing.daily_free_limit", minimum=1)
        ),
        cache_path=_expand_path(cache_path),
    )


def _parse_ranking(raw: Any) -> RankingConfig:
    section = _require_mapping(raw, "ranking")
    weights_raw = _require_mapping(section.get("weights", {}), "ranking.weights")
    weight_values: Dict[str, float] = {}
    for name in RankWeights.__dataclass_fields__:  # type: ignore[attr-defined]
        default = getattr(RankWeights(), name)
        weight_values[name] = _require_number(weights_raw.get(name, default), f"ranking.weights.{name}")
    return RankingConfig(
        weights=RankWeights(**weight_values),
        fallback_count=_require_int(section.get("fallback_count", 3), "ranking.fallback_count", minimum=0),
        fallbacks_allow_untested=_require_bool(
            section.get("fallbacks_allow_untested", False), "ranking.fallbacks_allow_untested"
        ),
        capacity_downgrade_after=_require_int(
            section.get("capacity_downgrade_after", 3), "ranking.capacity_downgrade_after", minimum=1
        ),
    )


def _parse_targets(raw: Any) -> List[TargetConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("targets must be a list of mappings")
    # Importing registers the built-in adapters so unknown names are rejected.
    from .adapters import available_adapters

    known = set(available_adapters())
    targets: List[TargetConfig] = []
    for index, item in enumerate(raw):
        where = f"targets[{index}]"
        section = _require_mapping(item, where)
        adapter = _require_str(section.get("adapter"), f"{where}.adapter")
        if adapter not in known:
            raise ConfigError(
                f"{where}.adapter: unknown adapter {adapter!r}; available: {', '.join(sorted(known)) or 'none'}"
            )
        path = _require_str(section.get("path"), f"{where}.path")
        options = _require_mapping(section.get("options") or {}, f"{where}.options")
        if "providers" in options:
            allowed = options["providers"]
            if (
                not isinstance(allowed, list)
                or not allowed
                or not all(isinstance(item, str) and item for item in allowed)
            ):
                raise ConfigError(f"{where}.options.providers must be a non-empty list of provider names")
        targets.append(TargetConfig(adapter=adapter, path=_expand_path(path), options=dict(options)))
    return targets


def _parse_backups(raw: Any) -> BackupConfig:
    section = _require_mapping(raw, "backups")
    keep = _require_int(section.get("keep", 5), "backups.keep", minimum=0)
    directory = section.get("dir")
    if directory is not None:
        directory = _expand_path(_require_str(directory, "backups.dir"))
    return BackupConfig(keep=keep, dir=directory)


def _parse_notify(raw: Any) -> NotifyConfig:
    # ``notify:`` with every channel commented out is an empty section.
    section = _require_mapping(raw if raw is not None else {}, "notify")

    def channel(name: str) -> Optional[Dict[str, Any]]:
        value = section.get(name)
        if value is None:
            return None
        settings = dict(_require_mapping(value, f"notify.{name}"))
        if "enabled" in settings:
            try:
                settings["enabled"] = parse_bool(settings["enabled"], name=f"notify.{name}.enabled", default=True)
            except ValueError as exc:
                raise ConfigError(str(exc)) from None
        return settings

    return NotifyConfig(telegram=channel("telegram"), webhook=channel("webhook"))


#: Keys accepted inside each section (``providers.<name>`` is open: its extra
#: keys are provider options).
_SECTION_KEYS: Dict[str, frozenset] = {
    "filters": frozenset(DEFAULT_CONFIG["filters"]),
    "testing": frozenset(DEFAULT_CONFIG["testing"]),
    "ranking": frozenset(DEFAULT_CONFIG["ranking"]),
    "ranking.weights": frozenset(RankWeights.__dataclass_fields__),  # type: ignore[attr-defined]
    "output": frozenset(DEFAULT_CONFIG["output"]),
    "backups": frozenset(DEFAULT_CONFIG["backups"]),
    "notify": frozenset(DEFAULT_CONFIG["notify"]),
    "notify.telegram": frozenset({"enabled", "bot_token_env", "chat_id_env"}),
    "notify.webhook": frozenset({"enabled", "url", "url_env"}),
    "targets[]": frozenset({"adapter", "path", "options"}),
}


def _unknown_section_keys(data: Mapping[str, Any]) -> List[str]:
    """Dotted names of keys inside sections that freemodel-sync does not use."""

    def section(path: str) -> Any:
        node: Any = data
        for part in path.split("."):
            node = node.get(part) if isinstance(node, Mapping) else None
        return node

    unknown: List[str] = []
    for path, known in _SECTION_KEYS.items():
        if path == "targets[]":
            targets = data.get("targets")
            items = list(enumerate(targets)) if isinstance(targets, list) else []
            for index, item in items:
                if isinstance(item, Mapping):
                    unknown += [f"targets[{index}].{key}" for key in item if key not in known]
            continue
        value = section(path)
        if isinstance(value, Mapping):
            unknown += [f"{path}.{key}" for key in value if key not in known]
    return unknown


def load_config(
    path: Optional[Union[str, os.PathLike]] = None,
    *,
    strict: bool = False,
) -> Config:
    """Load *path* (or the default config file) and return a :class:`Config`.

    A missing default config file yields the built-in defaults.  An explicitly
    given path that cannot be read raises :class:`ConfigError`, as do invalid
    YAML, invalid value types and unknown adapter names.  Unknown keys (a
    typo such as ``testing.max_test``) are logged as a warning; with
    ``strict=True`` they are rejected instead.
    """

    config_path = _expand_path(path) if path is not None else _default_path()
    explicit = path is not None

    data: Dict[str, Any] = {}
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config file {config_path}: {exc}") from exc
        try:
            loaded = yaml.safe_load(text) if text.strip() else None
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
        if loaded is None:
            loaded = {}
        if not isinstance(loaded, Mapping):
            raise ConfigError(f"{config_path} must contain a mapping at the top level, got {type(loaded).__name__}")
        data = dict(loaded)
    elif explicit:
        raise ConfigError(f"config file not found: {config_path}")

    unknown = sorted(str(key) for key in set(data) - set(DEFAULT_CONFIG)) + _unknown_section_keys(data)
    if unknown:
        if strict:
            raise ConfigError(f"unknown config key(s): {', '.join(unknown)}")
        LOG.warning(
            "%s: unknown config key(s) ignored (typo?): %s",
            config_path,
            ", ".join(unknown),
        )

    merged = _deep_merge(DEFAULT_CONFIG, data)
    if data.get("providers") is not None:
        # A user's providers section *replaces* the default (OpenRouter only):
        # listing providers means "use these", and OpenRouter can be dropped
        # or disabled with ``enabled: false``.
        merged["providers"] = copy.deepcopy(data["providers"])

    output_raw = _require_mapping(merged.get("output", {}), "output")
    ranking_json = output_raw.get("ranking_json")
    if ranking_json is not None:
        ranking_json = _expand_path(_require_str(ranking_json, "output.ranking_json"))
    state_path = _require_str(merged.get("state_path", DEFAULT_STATE_PATH), "state_path")

    notify = _parse_notify(merged.get("notify", {}))
    providers = _parse_providers(merged.get("providers", {}))
    manual_providers = _parse_manual_providers(merged.get("manual_providers", {}), providers)
    targets = _parse_targets(merged.get("targets", []))
    enabled = [name for name, cfg in providers.items() if cfg.enabled]
    selectable = set(providers) | set(manual_providers)
    for target in targets:
        allowed = target.options.get("providers")
        unknown = [name for name in allowed or [] if name not in selectable]
        if unknown:
            raise ConfigError(
                f"target {target.adapter} ({target.path}): options.providers lists "
                f"provider(s) not in the providers section: {', '.join(unknown)} "
                f"(manual_providers names are accepted too)"
            )
        if len(enabled) > 1 and not allowed:
            LOG.warning(
                "target %s (%s) has no options.providers but %d providers are enabled: "
                "its model may switch to another provider whose base URL needs a different "
                "API key. Set options.providers to the provider(s) this tool has a key for.",
                target.adapter,
                target.path,
                len(enabled),
            )
    if config_path.exists():
        _warn_inline_secrets(config_path, notify)

    return Config(
        providers=providers,
        manual_providers=manual_providers,
        filters=_parse_filters(merged.get("filters", {})),
        testing=_parse_testing(merged.get("testing", {})),
        ranking=_parse_ranking(merged.get("ranking", {})),
        output=OutputConfig(ranking_json=ranking_json),
        backups=_parse_backups(merged.get("backups", {})),
        state_path=_expand_path(state_path),
        targets=targets,
        notify=notify,
    )


def _warn_inline_secrets(config_path: Path, notify: NotifyConfig) -> None:
    """Warn when a webhook URL (which usually embeds a token) sits in the config file."""

    webhook = notify.webhook or {}
    if not webhook.get("url"):
        return
    LOG.warning(
        "notify.webhook.url is set in the config file; webhook URLs usually contain a "
        "token, so prefer notify.webhook.url_env and keep the URL in the environment"
    )
    try:
        mode = config_path.stat().st_mode & 0o777
    except OSError:
        return
    if os.name == "posix" and mode & 0o077:
        LOG.warning(
            "config file %s is readable by other users (mode %s) and contains a webhook URL; run: chmod 600 %s",
            config_path,
            oct(mode),
            config_path,
        )
