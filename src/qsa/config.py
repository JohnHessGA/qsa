"""Configuration loaders for QSA.

Two YAML files live under `config/`:

- `config/postgres.secrets.yaml` — DB credentials (gitignored).
- `config/qsa.yaml`              — application settings (thresholds, deprecated tables).

Credentials live exclusively in the YAML file. No env-var fallback —
see ``~/repos/notes/secrets-conventions.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def repo_root() -> Path:
    """Repo root — directory containing `config/`."""
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must be a mapping: {path}")
    return data


def load_postgres_config() -> dict[str, dict[str, Any]]:
    cfg = _load_yaml(repo_root() / "config" / "postgres.secrets.yaml")
    for required in ("masd", "shdb", "mefdb"):
        if required not in cfg:
            raise ConfigError(
                f"config/postgres.secrets.yaml missing required section: {required}"
            )
    return cfg


def load_app_config() -> dict[str, Any]:
    cfg = _load_yaml(repo_root() / "config" / "qsa.yaml")
    for required in (
        "min_valid_date",
        "future_date_tolerance_days",
        "staleness_thresholds_days",
        "mef_coverage",
        "deprecated_tables",
        "consumer_grep_repos",
    ):
        if required not in cfg:
            raise ConfigError(f"config/qsa.yaml missing required section: {required}")
    return cfg
