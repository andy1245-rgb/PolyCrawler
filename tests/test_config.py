from pathlib import Path

from polycrawler.config import Config, configHash, loadConfig

basePath = Path(__file__).parents[1] / "configs" / "base.yaml"


def testLoadConfigMatchesDefaultsAndHashIsStable() -> None:
    loaded = loadConfig(basePath, [])
    again = loadConfig(basePath, [])
    assert loaded == Config()
    assert configHash(loaded) == configHash(again)
    digest = configHash(loaded)
    assert configHash(loaded) == configHash(Config())
    assert len(digest) == 12
    assert all(char in "0123456789abcdef" for char in digest)


def testOverridesDottedPathAndChangeHash() -> None:
    overrides = [
        "strategy.delaySec=60",
        "fetch.eventSlugs=[cbb-valp-uic-2025-03-06, other]",
        "fetch.closedOnly=false",
        "discovery.excludedFunders=['0xabc']",
    ]
    base = loadConfig(basePath, [])
    changed = loadConfig(basePath, overrides)
    assert changed.strategy.delaySec == 60
    assert changed.fetch.eventSlugs == ["cbb-valp-uic-2025-03-06", "other"]
    assert changed.fetch.closedOnly is False
    assert changed.discovery.excludedFunders == ["0xabc"]
    assert configHash(base) != configHash(changed)
    assert configHash(changed) == configHash(loadConfig(basePath, overrides))
