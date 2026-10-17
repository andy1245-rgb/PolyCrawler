"""OOS failure diagnosis: WHY the military fresh-longshot copy line dies
out-of-sample. Exploratory diagnosis — hypothesis tests, not rule tuning.

Reuses entrySweep machinery by importlib-by-path (loadEntries entries caches,
filterCell cell selection, evaluate seeded event-level bootstrap). Nothing
about the shipped rule is re-derived; the cell is selected, then the five
pre-registered questions in research/oosFailureDiagnosis.md are graded on the
in-sample dirs [data, data/universe] and the OOS dir [data/oosExpansion]
SEPARATELY (never mixed in one number):

  Q1 velocity   post-burst print drift (up = continuation, down = mean-reversion)
                at T+1h/T+6h/T+1d from burst END, vs burst average price
                (recomputed from fills — the cached `price` is the TRIGGER
                print), by dir-set and half-year bucket
  Q2 fade test  the OPPOSITE side of the same burst: complement at
                (1 − nextPrint)(1+50bps) held to resolution, entries with a
                next print ≤300s, binary markets only
  Q3 population shift of the rule's trigger population ($5k/≤0.35/≤5d/≤3mkts):
                day-0/1 share, burst size, copy-price buckets, era mix,
                feesEnabled/negRisk columns (reported if absent)
  Q4 concentration of the flagship cell's per-event PnL (per-event ONLY)
  Q5 history weight   OOS split at 2026-01-01: pre-2026 era vs pure 2026 era

RSS discipline: fills are lazy-scanned with selective projections, restricted
to the cell's marketIds before any collect.

Run: uv run python scripts/research/oosFailureDiagnosis.py 2>&1 \
        | tee logs/oosFailureDiagnosis.log
"""

import argparse
import importlib.util
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

t0 = time.time()
ROOT = Path(__file__).resolve().parents[2]
SLIP = 0.005  # 50bps, oosTransport convention on the delayed/fade fill

_spec = importlib.util.spec_from_file_location(
    "esw", ROOT / "scripts" / "research" / "entrySweep.py")
esw = importlib.util.module_from_spec(_spec)
sys.modules["esw"] = esw
_spec.loader.exec_module(esw)
_spec = importlib.util.spec_from_file_location(
    "researchData", ROOT / "scripts" / "research" / "researchData.py")
researchData = importlib.util.module_from_spec(_spec)
sys.modules["researchData"] = researchData
_spec.loader.exec_module(researchData)

FLAGSHIP = {"minUsd": 10000.0, "maxPrice": 0.35, "ageDays": 5.0, "marketsSoFar": 3}
POPULATION = {"minUsd": 5000.0, "maxPrice": 0.35, "ageDays": 5.0, "marketsSoFar": 3}
DURS = [("T+1h", 3600), ("T+6h", 21600), ("T+1d", 86400)]
ERAS = [(datetime(2023, 10, 1, tzinfo=UTC), datetime(2024, 7, 1, tzinfo=UTC), "23H2-24H1"),
        (datetime(2024, 7, 1, tzinfo=UTC), datetime(2025, 7, 1, tzinfo=UTC), "24H2-25H1"),
        (datetime(2025, 7, 1, tzinfo=UTC), datetime(2099, 1, 1, tzinfo=UTC), "25H2+")]
Q5CUT = datetime(2026, 1, 1, tzinfo=UTC)

def buildEra(col: str) -> pl.Expr:
    ts = pl.col(col)
    out = pl.lit("23H2-24H1")
    for lo, hi, name in ERAS:
        out = pl.when((ts >= pl.lit(lo)) & (ts < pl.lit(hi))).then(pl.lit(name).cast(pl.String)).otherwise(out)
    return out


def q1Velocity(dirs: list[str], cell: pl.DataFrame) -> pl.DataFrame:
    mids = cell["marketId"].unique().to_list()
    lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet") for d in dirs], how="diagonal_relaxed")
    buysL = (lazy.filter((pl.col("side") == "BUY") & pl.col("marketId").is_in(mids))
             .select("ts", "account", "marketId", "outcome", "size", "price"))
    bursts = (buysL.sort("account", "marketId", "outcome", "ts")
              .with_columns(burst=(pl.col("ts").diff().over("account", "marketId", "outcome")
                                   .fill_null(pl.duration(days=1)) > pl.duration(minutes=10))
                            .cum_sum().over("account", "marketId", "outcome"))
              .group_by("account", "marketId", "outcome", "burst")
              .agg(ts=pl.col("ts").min(), burstEnd=pl.col("ts").max(),
                   usdR=(pl.col("size") * pl.col("price")).sum(), sharesR=pl.col("size").sum())
              .with_columns(avg=pl.col("usdR") / pl.col("sharesR"))
              .drop("burst", "usdR", "sharesR")
              .collect())
    base = (cell.join(bursts, on=["account", "marketId", "outcome", "ts"], how="inner", validate="1:1")
            .with_columns(era=buildEra("ts")))
    mismatch = (base["avg"] - base["price"]).abs().max()
    print(f"  burst-avg recompute sanity: |avg − cached trigger price| max = {mismatch}", flush=True)
    tape = (buysL.select("ts", "marketId", "outcome", "price")
            .sort("ts", "marketId", "outcome").collect())
    base = base.with_row_index("row")
    rows = []
    for label, dur in DURS:
        tgt = (base.select("row", "marketId", "outcome", "burstEnd",
                           (pl.col("burstEnd") + pl.duration(seconds=dur)).alias("target"))
               .sort("target"))
        j = (tgt.join_asof(tape, left_on="target", right_on="ts",
                           by=["marketId", "outcome"], strategy="backward")
             .filter(pl.col("ts") > pl.col("burstEnd"))
             .select(pl.col("row"), pl.col("price").alias("vprice")))
        df = (base.join(j, on="row", how="inner")
              .with_columns(drift=pl.col("vprice") - pl.col("avg"),
                            rel=pl.col("vprice") / pl.col("avg") - 1))
        for era, g in df.group_by("era", maintain_order=True):
            era = era[0]
            rows.append({"dir": "", "era": era, "win": label,
                         "n": g.height,
                         "cov%": round(100 * g.height / max(df.filter(pl.col("era") == era).height, 1), 1),
                         "meanDrift": round(g["drift"].mean(), 4),
                         "medDrift": round(g["drift"].median(), 4),
                         "meanRel%": round(100 * g["rel"].mean(), 1),
                         "medRel%": round(100 * g["rel"].median(), 1),
                         "down%": round(100 * (g["drift"] < 0).mean(), 1)})
    out = pl.DataFrame(rows).sort(["era", "win"], descending=[False, False])
    # dir label filled by caller
    return out


def q2Fade(dirs: list[str], cell: pl.DataFrame) -> pl.DataFrame:
    mids = cell["marketId"].unique().to_list()
    lazy = pl.concat([pl.scan_parquet(f"{d}/fills.parquet") for d in dirs], how="diagonal_relaxed")
    buysL = lazy.filter((pl.col("side") == "BUY") & pl.col("marketId").is_in(mids))
    nextP = (buysL.select("ts", "marketId", "outcome", "price")
             .sort("marketId", "outcome", "ts")
             .with_columns(nextTs=pl.col("ts").shift(-1).over("marketId", "outcome"),
                           nextPrice=pl.col("price").shift(-1).over("marketId", "outcome"))
             .unique(subset=["ts", "marketId", "outcome"], keep="last")
             .collect())
    binary = (buysL.group_by("marketId").agg(nout=pl.col("outcome").n_unique())
              .filter(pl.col("nout") == 2).select("marketId")
              .collect())
    gap = (pl.col("nextTs") - pl.col("ts")).dt.total_seconds()
    df = (cell.join(nextP.select("ts", "marketId", "outcome", "nextTs", "nextPrice"),
                    on=["ts", "marketId", "outcome"], how="left")
          .with_columns(landed=(pl.col("nextPrice").is_not_null() & (gap <= 300)))
          .filter(pl.col("landed"))
          .join(binary, on="marketId", how="inner")
          .with_columns(era=buildEra("ts"),
                        cost=(1 - pl.col("nextPrice")) * (1 + SLIP),
                        fadeWon=pl.col("outcome") != pl.col("winner")))
    df = df.with_columns(
        retReal=pl.when(pl.col("outcome") == pl.col("winner")).then(-1.0)
        .otherwise(1 / pl.col("cost") - 1))
    rows = []
    for era, g in df.group_by("era"):
        era = era[0]
        ev = esw.evaluate(g, random.Random(7))
        rows.append({"dir": "", "era": era, "n": g.height, "events": ev.get("events"),
                     "fadeRet": ev.get("ret"), "medPnl": round(g["retReal"].median(), 3),
                     "compWin%": round(100 * g["fadeWon"].mean(), 1),
                     "p5": ev.get("p5"), "P>0": ev.get("p")})
    ev = esw.evaluate(df, random.Random(7))
    rows.append({"dir": "", "era": "ALL", "n": df.height, "events": ev.get("events"),
                 "fadeRet": ev.get("ret"), "medPnl": round(df["retReal"].median(), 3),
                 "compWin%": round(100 * df["fadeWon"].mean(), 1),
                 "p5": ev.get("p5"), "P>0": ev.get("p")})
    return pl.DataFrame(rows).sort("era"), df


def q4Concentration(cell: pl.DataFrame) -> dict:
    ev = (cell.group_by("eventSlug")
          .agg(pnl=(pl.col("retReal") * 100).sum(), n=pl.len())
          .sort("pnl", descending=True))
    tot = ev["pnl"].sum()
    return {"events": ev.height, "total": round(tot, 1),
            "mean": round(ev["pnl"].mean(), 1), "median": round(ev["pnl"].median(), 1),
            "max": round(ev["pnl"].max(), 1), "min": round(ev["pnl"].min(), 1),
            "topEvent": ev["eventSlug"][0], "topPnl": round(ev["pnl"][0], 1),
            "topShare%": round(100 * ev["pnl"][0] / tot, 1) if tot > 0 else 100.0,
            "posEvents": int((ev["pnl"] > 0).sum()),
            "le1000": int((ev["pnl"] <= -1000).sum()),
            "meanEntriesPerEvent": round(cell.height / ev.height, 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    dirsets = {"in-sample": [str(p) for p in researchData.researchDataDirs()],
               "oos": [str(ROOT / "data" / "oosExpansion")]}
    for name, dirs in dirsets.items():
        entries = esw.loadEntries(dirs, args.refresh)
        cell = esw.filterCell(entries, FLAGSHIP)
        pop = esw.filterCell(entries, POPULATION)
        print(f"\n{'=' * 100}\ndir-set {name}: {dirs}\n"
              f"flagship cell n={cell.height} events={cell['eventSlug'].n_unique()} "
              f"accts={cell['account'].n_unique()} ({time.time() - t0:.0f}s)", flush=True)

        print(f"\n--- Q1 velocity ({name}): post-burst print drift vs burst avg ---", flush=True)
        v = q1Velocity(dirs, cell)
        v = v.with_columns(pl.lit(name).alias("dir"))
        print(v)

        print(f"\n--- Q2 fade ({name}): complement side of the same burst ---", flush=True)
        f, fdf = q2Fade(dirs, cell)
        f = f.with_columns(pl.lit(name).alias("dir"))
        print(f)
        pos = int((fdf["retReal"] > 0).sum())
        print(f"  fade pnl>0 entries: {pos}/{fdf.height} "
              f"mean pnl {fdf['retReal'].mean():.3f} ", flush=True)

        print(f"\n--- Q3 population ({name}): rule trigger population ---", flush=True)
        mk = pl.concat([pl.read_parquet(f"{d}/markets.parquet") for d in dirs], how="diagonal_relaxed")
        feeCols = [c for c in mk.columns if "fee" in c.lower() or "neg" in c.lower()]
        print(f"  markets.parquet fee/negRisk columns: {feeCols or 'ABSENT — not gradeable'}",
              flush=True)
        usd = pop["usd"].quantile(0.5), pop["usd"].quantile(0.25), pop["usd"].quantile(0.75)
        n = pop.height
        rows = {"dir": name, "n": n, "events": pop["eventSlug"].n_unique(),
                "day01%": round(100 * (pop["ageDays"] <= 1).mean(), 1),
                "usdMed": round(usd[0]), "usdP25": round(usd[1]), "usdP75": round(usd[2]),
                "px<=0.2%": round(100 * (pop["price"] <= 0.2).mean(), 1),
                "mkt=1%": round(100 * (pop["marketsSoFar"] == 1).mean(), 1)}
        for _, _, era in ERAS:
            sub = pop.filter(buildEra("ts") == era)
            rows[era] = round(100 * sub.height / max(n, 1), 1)
        print(pl.DataFrame(rows))

        print(f"\n--- Q4 concentration ({name}): per-event PnL, flagship cell ---", flush=True)
        print(q4Concentration(cell))

        print(f"\n--- Q5 history weight ({name}): era split at 2026-01-01 ---", flush=True)
        rows = []
        for label, df in [("pre-2026", cell.filter(pl.col("ts") < Q5CUT)),
                          ("2026+", cell.filter(pl.col("ts") >= Q5CUT))]:
            ev = esw.evaluate(df, random.Random(7))
            rows.append({"dir": name, "era": label, "n": df.height,
                         "events": ev.get("events"),
                         "retReal": ev.get("ret"),
                         "winRate%": round(100 * df["won"].mean(), 1) if df.height else None,
                         "p5": ev.get("p5"), "P>0": ev.get("p")})
        print(pl.DataFrame(rows))
        print(f"\ndone dir-set {name} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
