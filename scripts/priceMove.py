"""Load the local tape and write the price-move check to research/priceMove.md."""

from pathlib import Path

import polars as pl

from polycrawler.priceMove import buildReport


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fills = pl.read_parquet(
        root / "data" / "fills.parquet",
        columns=["ts", "account", "marketId", "outcome", "side", "size", "price"],
    )
    markets = pl.read_parquet(
        root / "data" / "markets.parquet",
        columns=["marketId", "question", "winner", "resolvedAt", "outcomes"],
    )
    suspicious = pl.read_parquet(root / "data" / "suspicious.parquet")
    labels = pl.read_csv(root / "research" / "knownWallets.csv")
    text = buildReport(fills, markets, suspicious, labels)
    out = root / "research" / "priceMove.md"
    out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
