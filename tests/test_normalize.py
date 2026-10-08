import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from polycrawler.fetch import (
    dedupeFills,
    fillDedupeKeys,
    fillSchema,
    normalizeEvent,
    normalizeFill,
    upsertTable,
    winnerFrom,
)

fixtures = Path(__file__).parent / "fixtures"


def testNormalizeResolvedEvent() -> None:
    event = json.loads((fixtures / "event.json").read_text())
    rows = normalizeEvent(event, closedOnly=True)
    assert len(rows) == 1
    market = rows[0]
    assert market["marketId"] == "0x4b343a91e4892e769d1f6bba3b88239e49311ccbd0e4be2fa165a8c2935a37b1"
    assert market["eventSlug"] == "cbb-valp-uic-2025-03-06"
    assert market["question"] == "Valparaiso vs. UIC"
    assert market["tags"] == ["sports", "basketball"]
    assert market["winner"] == "Valparaiso"
    assert market["volumeUsd"] == 500
    assert market["outcomes"] == ["Valparaiso", "UIC"]
    assert market["clobTokenIds"][0].startswith("6404773687")
    assert market["endDate"] == datetime(2025, 3, 6, tzinfo=timezone.utc)


def testWinnerIsNullUnlessOnePriceIsOne() -> None:
    assert winnerFrom(["Yes", "No"], ["0", "1"]) == "No"
    assert winnerFrom(["Yes", "No"], ["0.2", "0.8"]) is None
    assert winnerFrom(["Yes", "No"], ["0", "0"]) is None
    assert winnerFrom(["Yes", "No"], ["1", "1"]) is None


def testNormalizeFillsAndDedupe() -> None:
    raw = json.loads((fixtures / "trades.json").read_text())
    fills = [normalizeFill(row) for row in raw]
    fills.append(dict(fills[0]))
    fills = dedupeFills(fills)
    assert len(fills) == 2
    assert fills[0]["account"] == "0x480d013bf6665fb174fb7ec6ea677cfc8140f219"
    assert fills[0]["side"] == "BUY"
    assert fills[0]["size"] == 500
    assert fills[0]["price"] == 0.6483
    assert fills[0]["txHash"].startswith("0x97528a20")
    assert fills[0]["ts"] == datetime.fromtimestamp(1741310607, tz=timezone.utc)
    assert fills[0]["outcome"] == "UIC"
    assert fills[1]["account"].startswith("0x29c0a89b")


def testUpsertDedupesFills(tmp_path: Path) -> None:
    raw = json.loads((fixtures / "trades.json").read_text())
    fills = [normalizeFill(row) for row in raw]
    path = tmp_path / "fills.parquet"
    upsertTable(path, fills, fillSchema, fillDedupeKeys, ["ts"])
    upsertTable(path, fills, fillSchema, fillDedupeKeys, ["ts"])
    frame = pl.read_parquet(path)
    assert frame.height == 2
    assert set(frame.columns) >= set(fillDedupeKeys)
