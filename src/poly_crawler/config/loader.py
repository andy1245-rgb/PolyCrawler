"""Config loader: YAML defaults → env vars → user override → validated Pydantic model."""

from pathlib import Path

import yaml

from .schema import Config


def _load_yaml(path: Path) -> dict:
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
    """
    defaults = _load_yaml(Path(default_path))

    overrides = {}
    if override_path:
        overrides = _load_yaml(Path(override_path))

    merged = {**defaults, **overrides}
    return Config(**merged)
