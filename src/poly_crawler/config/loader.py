"""Config loader: YAML defaults → user override → env vars → validated model.

Priority (highest last / wins):
1. Pydantic field defaults
2. ``config/default.yaml``
3. File from ``override_path`` or ``POLY_CONFIG``
4. Environment variables prefixed with ``POLY_``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .schema import Config


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base without clobbering nested keys."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    default_path: Path | str = "config/default.yaml",
    override_path: Path | str | None = None,
) -> Config:
    """Load config with layered overrides.

    Order: Pydantic defaults → YAML defaults → override YAML → env vars.
    ``POLY_CONFIG`` is used when *override_path* is not passed explicitly.
    """
    defaults = _load_yaml(Path(default_path))

    resolved_override = override_path
    if resolved_override is None:
        resolved_override = os.environ.get("POLY_CONFIG")

    overrides: dict[str, Any] = {}
    if resolved_override:
        overrides = _load_yaml(Path(resolved_override))

    merged = _deep_merge(defaults, overrides)
    return Config(**merged)
