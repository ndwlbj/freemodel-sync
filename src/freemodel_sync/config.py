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
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union

import yaml

from .ranking import RankWeights

DEFAULT_CONFIG_PATH = "~/.config/freemodel-sync/config.yml"
DEFAULT_CACHE_PATH = "~/.cache/freemodel-sync/results.json"
DEFAULT_STATE_PATH = "~/.local/state/freemodel-sync/state.json"

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
        },
        "fallback_count": 3,
    },
    "output": {"ranking_json": None},
    "backups": {"keep": 5, "dir": None},
    "state_path": DEFAULT_STATE_PATH,
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
class FilterConfig(_Section):
    require_tools: bool = False
    min_context: int = 0
    exclude_expiring_within_days: Optional[int] = 3
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


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
        default_factory=lambda: {
            "openrouter": ProviderConfig(enabled=True, api_key_env="OPENROUTER_API_KEY")
        }
    )
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
            str(name): value
            if isinstance(value, ProviderConfig)
            else ProviderConfig(**dict(value))
            for name, value in self.providers.items()
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
            )
        if not isinstance(self.output, OutputConfig):
            self.output = OutputConfig(**dict(self.output))
        if not isinstance(self.backups, BackupConfig):
            self.backups = BackupConfig(**dict(self.backups))
        if not isinstance(self.notify, NotifyConfig):
            self.notify = NotifyConfig(**dict(self.notify))
        self.state_path = _expand_path(self.state_path)
        self.targets = [
            target
            if isinstance(target, TargetConfig)
            else TargetConfig(**dict(target))
            for target in self.targets
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


def _parse_providers(raw: Any) -> Dict[str, ProviderConfig]:
    mapping = _require_mapping(raw, "providers")
    providers: Dict[str, ProviderConfig] = {}
    for name, value in mapping.items():
        where = f"providers.{name}"
        section = _require_mapping(value, where)
        enabled = _require_bool(section.get("enabled", True), f"{where}.enabled")
        api_key_env = section.get("api_key_env", "OPENROUTER_API_KEY")
        if api_key_env is None:
            api_key_env = ""
        elif not isinstance(api_key_env, str):
            raise ConfigError(f"{where}.api_key_env must be a string or null")
        extra = {
            key: item
            for key, item in section.items()
            if key not in {"enabled", "api_key_env"}
        }
        providers[str(name)] = ProviderConfig(
            enabled=enabled, api_key_env=api_key_env, options=extra
        )
    return providers


def _parse_filters(raw: Any) -> FilterConfig:
    section = _require_mapping(raw, "filters")
    min_context = _require_int(section.get("min_context", 0), "filters.min_context", minimum=0)
    expiring = section.get("exclude_expiring_within_days", 3)
    if expiring is not None:
        expiring = _require_int(
            expiring, "filters.exclude_expiring_within_days", minimum=0
        )
    return FilterConfig(
        require_tools=_require_bool(
            section.get("require_tools", False), "filters.require_tools"
        ),
        min_context=min_context,
        exclude_expiring_within_days=expiring,
        include=_optional_str_list(section.get("include", []), "filters.include"),
        exclude=_optional_str_list(section.get("exclude", []), "filters.exclude"),
    )


def _parse_testing(raw: Any) -> TestingConfig:
    section = _require_mapping(raw, "testing")
    cache_path = section.get("cache_path", DEFAULT_CACHE_PATH)
    cache_path = _require_str(cache_path, "testing.cache_path")
    return TestingConfig(
        max_tests=_require_int(section.get("max_tests", 5), "testing.max_tests", minimum=0),
        cache_ttl_hours=_require_number(
            section.get("cache_ttl_hours", 6), "testing.cache_ttl_hours", positive=True
        ),
        transient_ttl_minutes=_require_number(
            section.get("transient_ttl_minutes", 30), "testing.transient_ttl_minutes", positive=True
        ),
        timeout_s=_require_number(
            section.get("timeout_s", 30), "testing.timeout_s", positive=True
        ),
        reserve_requests=_require_int(
            section.get("reserve_requests", 10), "testing.reserve_requests", minimum=0
        ),
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
        weight_values[name] = _require_number(
            weights_raw.get(name, default), f"ranking.weights.{name}"
        )
    return RankingConfig(
        weights=RankWeights(**weight_values),
        fallback_count=_require_int(
            section.get("fallback_count", 3), "ranking.fallback_count", minimum=0
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
                f"{where}.adapter: unknown adapter {adapter!r}; "
                f"available: {', '.join(sorted(known)) or 'none'}"
            )
        path = _require_str(section.get("path"), f"{where}.path")
        options = _require_mapping(section.get("options") or {}, f"{where}.options")
        targets.append(
            TargetConfig(adapter=adapter, path=_expand_path(path), options=dict(options))
        )
    return targets


def _parse_backups(raw: Any) -> BackupConfig:
    section = _require_mapping(raw, "backups")
    keep = _require_int(section.get("keep", 5), "backups.keep", minimum=0)
    directory = section.get("dir")
    if directory is not None:
        directory = _expand_path(_require_str(directory, "backups.dir"))
    return BackupConfig(keep=keep, dir=directory)


def _parse_notify(raw: Any) -> NotifyConfig:
    section = _require_mapping(raw, "notify")

    def channel(name: str) -> Optional[Dict[str, Any]]:
        value = section.get(name)
        if value is None:
            return None
        return dict(_require_mapping(value, f"notify.{name}"))

    return NotifyConfig(telegram=channel("telegram"), webhook=channel("webhook"))


def load_config(
    path: Optional[Union[str, os.PathLike]] = None,
    *,
    strict: bool = False,
) -> Config:
    """Load *path* (or the default config file) and return a :class:`Config`.

    A missing default config file yields the built-in defaults.  An explicitly
    given path that cannot be read raises :class:`ConfigError`, as do invalid
    YAML, invalid value types and unknown adapter names.  With ``strict=True``
    unknown top-level keys are rejected as well.
    """

    explicit = path is not None
    config_path = _expand_path(path) if explicit else _default_path()

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
            raise ConfigError(
                f"{config_path} must contain a mapping at the top level, "
                f"got {type(loaded).__name__}"
            )
        data = dict(loaded)
    elif explicit:
        raise ConfigError(f"config file not found: {config_path}")

    if strict:
        unknown = sorted(set(data) - set(DEFAULT_CONFIG))
        if unknown:
            raise ConfigError(f"unknown config key(s): {', '.join(unknown)}")

    merged = _deep_merge(DEFAULT_CONFIG, data)

    output_raw = _require_mapping(merged.get("output", {}), "output")
    ranking_json = output_raw.get("ranking_json")
    if ranking_json is not None:
        ranking_json = _expand_path(_require_str(ranking_json, "output.ranking_json"))
    state_path = _require_str(merged.get("state_path", DEFAULT_STATE_PATH), "state_path")

    return Config(
        providers=_parse_providers(merged.get("providers", {})),
        filters=_parse_filters(merged.get("filters", {})),
        testing=_parse_testing(merged.get("testing", {})),
        ranking=_parse_ranking(merged.get("ranking", {})),
        output=OutputConfig(ranking_json=ranking_json),
        backups=_parse_backups(merged.get("backups", {})),
        state_path=_expand_path(state_path),
        targets=_parse_targets(merged.get("targets", [])),
        notify=_parse_notify(merged.get("notify", {})),
    )
