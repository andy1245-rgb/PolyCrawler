"""Config loader: YAML defaults → env vars → user override → validated Pydantic model."""

from pathlib import Path
from typing import Any

import yaml

from .schema import Config


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def load_config(
    default_path: Path | str = "config/default.yaml",
    override_path: Path | str | None = None,
) -> Config:
    """Load config with layered overrides.

    Order: Pydantic defaults → YAML defaults → env vars → user YAML override.

    Top-level ``null`` values for ``database_url`` / ``rpc_url`` are omitted so
    ``POLY_DATABASE_URL`` / ``POLY_RPC_URL`` env vars can take effect.
    """
    defaults = _load_yaml(Path(default_path))

    overrides: dict[str, Any] = {}
    if override_path:
        overrides = _load_yaml(Path(override_path))

    merged = {**defaults, **overrides}
    for key in ("database_url", "rpc_url"):
        if merged.get(key) is None:
            merged.pop(key, None)
    return Config(**merged)
