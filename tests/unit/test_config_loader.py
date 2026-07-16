"""Unit tests for config loading: YAML layers, deep merge, POLY_CONFIG, env."""

from __future__ import annotations

from pathlib import Path

import yaml

from poly_crawler.config.loader import load_config
from poly_crawler.config.schema import Config


def test_load_default_yaml() -> None:
    config = load_config("config/default.yaml")
    assert config.execution.mode == "paper"
    assert config.discovery.min_sibling_count == 2
    assert config.discovery.profit_formula == "sqrt"
    assert config.entry.min_buy_usd == 500.0
    assert config.rpc_url is None


def test_deep_merge_preserves_nested_defaults(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    override_path = tmp_path / "override.yaml"
    default_path.write_text(
        yaml.dump(
            {
                "discovery": {
                    "min_sibling_count": 5,
                    "funding_hops": 7,
                    "profit_formula": "log",
                },
                "entry": {"min_buy_usd": 100.0},
            }
        )
    )
    override_path.write_text(
        yaml.dump(
            {
                "discovery": {"profit_formula": "sqrt"},
                "sessions": {"private_default": True},
            }
        )
    )

    config = load_config(default_path, override_path)
    assert config.discovery.min_sibling_count == 5
    assert config.discovery.funding_hops == 7
    assert config.discovery.profit_formula == "sqrt"
    assert config.entry.min_buy_usd == 100.0
    assert config.sessions.private_default is True


def test_poly_config_env_loads_override(tmp_path: Path, monkeypatch) -> None:
    override_path = tmp_path / "prod.yaml"
    override_path.write_text(yaml.dump({"sessions": {"private_default": True}}))
    monkeypatch.setenv("POLY_CONFIG", str(override_path))

    config = load_config("config/default.yaml")
    assert config.sessions.private_default is True
    assert config.discovery.min_sibling_count == 2


def test_env_var_overrides_yaml(monkeypatch) -> None:
    monkeypatch.setenv("POLY_ENTRY__MIN_BUY_USD", "999")
    config = load_config("config/default.yaml")
    assert config.entry.min_buy_usd == 999.0


def test_production_yaml_override() -> None:
    config = load_config("config/default.yaml", "config/production.yaml")
    assert config.sessions.private_default is True
    assert config.retention.raw_trades_days == 365
    assert config.discovery.min_sibling_count == 2
    assert config.execution.mode == "paper"


def test_config_defaults_without_yaml() -> None:
    config = Config()
    assert config.execution.mode == "paper"
    assert config.review.mode == "live_only"
