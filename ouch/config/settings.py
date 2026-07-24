"""Global config model + discovery/precedence (spec §5).

Precedence (highest wins):
  1. Command-line flags  2. Environment (OUCH_*)  3. Scenario patch
  4. Profile file        5. config.toml           6. Built-in defaults
Every resolved value records its origin for `ouch config show --origin`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from ouch.errors import ConfigError

DEFAULTS: dict[str, object] = {
    "general.default_profile": "default",
    "general.tax_year": "current",
    "general.currency": "USD",
    "general.color": "auto",
    "general.confirm_destructive": True,
    "output.format": "table",
    "output.verbosity": 1,
    "output.round_display": "dollar",
    "output.show_citations": True,
    "taxdata.path": "",
    "taxdata.strict_year": True,
    "taxdata.allow_projected": False,
    "privacy.encrypt_profiles": False,
    "privacy.redact_in_logs": True,
    "ai.enabled": False,
    "ai.provider": "anthropic",
    "ai.model": "claude-opus-5",     # configurable; see provider docs
    "ai.api_key_env": "ANTHROPIC_API_KEY",
    "ai.require_confirmation": True,
    "ai.transcript_log": False,
}

ENV_MAP = {
    "OUCH_PROFILE": "general.default_profile",
    "OUCH_TAX_YEAR": "general.tax_year",
    "OUCH_TAXDATA": "taxdata.path",
    "OUCH_AI_ENABLED": "ai.enabled",
}


def config_dir() -> Path:
    return Path(user_config_dir("ouch"))


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def profiles_dir() -> Path:
    return config_dir() / "profiles"


@dataclass
class Settings:
    values: dict[str, object] = field(default_factory=dict)
    origins: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)

    def set(self, key: str, value: object, origin: str) -> None:
        self.values[key] = value
        self.origins[key] = origin


def _flatten(prefix: str, table: dict, out: dict[str, object]) -> None:
    for k, v in table.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(key, v, out)
        else:
            out[key] = v


def load_settings(config_path: Path | None = None) -> Settings:
    s = Settings()
    for key, value in DEFAULTS.items():
        s.set(key, value, "default")

    path = config_path or (
        Path(os.environ["OUCH_CONFIG"]).expanduser()
        if os.environ.get("OUCH_CONFIG") else default_config_path())
    if path.is_file():
        try:
            raw = tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"malformed config file {path}: {e}") from e
        flat: dict[str, object] = {}
        _flatten("", raw, flat)
        for key, value in flat.items():
            s.set(key, value, str(path))

    for env, key in ENV_MAP.items():
        if env in os.environ:
            s.set(key, os.environ[env], f"env {env}")
    if os.environ.get("OUCH_NO_COLOR") or os.environ.get("NO_COLOR"):
        s.set("general.color", "never", "env NO_COLOR")
    return s


def resolve_tax_year(settings: Settings, override: int | None,
                     today_year: int) -> int:
    if override is not None:
        return override
    raw = settings.get("general.tax_year", "current")
    if raw == "current" or raw is None:
        return today_year
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise ConfigError(
            f"invalid tax_year '{raw}' in config",
            hint="use a year like 2026 or the string \"current\"") from e
