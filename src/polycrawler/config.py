import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class FetchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventSlugs: list[str] = Field(default_factory=list)
    marketTags: list[str] = Field(default_factory=lambda: ["politics", "geopolitics"])
    minMarketVolumeUsd: float = 100000
    fromDate: date = date(2024, 1, 1)
    closedOnly: bool = True
    dataDir: str = "data"


class DiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maxAccountAgeDays: int = 14
    maxMarketsTraded: int = 5
    maxBuyPrice: float = 0.3
    minBetUsd: float = 1000
    minSignals: int = 4
    minSuspiciousAccounts: int = 2
    excludedFunders: list[str] = Field(default_factory=list)
    hubMinCounterparties: int = 50
    fundingHops: int = 2
    minFundingUsd: float = 1
    minBridgeDepositUsd: float = 100
    # Relay solver. Other payout hubs are added when a sample tx resolves on Relay.
    bridgeHubs: list[str] = Field(
        default_factory=lambda: ["0xf70da97812cb96acdf810712aa562db8dfa3dbef"]
    )
    bridgeProbeLimit: int = 3
    coTradeWindowSec: int = 10
    minCoTrades: int = 2
    relayRequestsPerSec: float = 1.0
    relayPageLimit: int = 50
    httpMaxWorkers: int = 8


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minNetUsd: float = 500
    maxEntryPrice: float = 0.5
    mirrorPct: float = 1.0
    maxPositionUsd: float = 1000
    exitMode: Literal["followCluster", "holdToResolution"] = "followCluster"
    delaySec: int = 30
    slippageBps: int = 50


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    splitDate: date = date(2026, 1, 1)
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)


def loadConfig(path: str | Path, overrides: list[str] | None = None) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping: {path}")
    for item in overrides or []:
        applyOverride(raw, item)
    return Config.model_validate(raw)


def applyOverride(raw: dict[str, Any], item: str) -> None:
    if "=" not in item:
        raise ValueError(f"override must look like strategy.delaySec=60, got {item!r}")
    dotted, valueText = item.split("=", 1)
    parts = [part for part in dotted.split(".") if part]
    if not parts:
        raise ValueError(f"override path is empty: {item!r}")
    value = yaml.safe_load(valueText)
    cursor = raw
    for part in parts[:-1]:
        nxt = cursor.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = value


def configHash(config: Config) -> str:
    payload = config.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
