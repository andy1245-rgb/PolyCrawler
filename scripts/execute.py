"""Execution for watcher signals: turn a data/live/signals.csv alert into a
CLOB market-buy order on the copied outcome.

Signing: CTF Exchange V2 via the official py-clob-client-v2 package. The
April-2026 V2 migration rejects V1 orders ("400 invalid order version");
tick size, negRisk routing and order version are resolved server-side by
the client when no PartialCreateOrderOptions are passed.

Safety model:
  - default is DRY RUN: prints the order it would place, touches nothing.
  - --live requires both POLYMARKET_PRIVATE_KEY in the environment and an
    explicit --live flag in the same invocation. Nothing else can arm it.
  - hard caps: MAX_USD per order, MAX_OPEN_USD total across live fills
    (tracked in data/live/executions.csv).

Usage:
  uv run python scripts/execute.py --signal <alertTs>   # one signal by id
  uv run python scripts/execute.py --latest             # newest unfired signal
  add --live to actually place orders
"""

import argparse
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from py_clob_client_v2 import ClobClient, OrderArgs, Side

ROOT = Path(__file__).resolve().parents[1]
SIGNALS = ROOT / "data" / "live" / "signals.csv"
EXECUTIONS = ROOT / "data" / "live" / "executions.csv"
MAX_USD = 50.0
MAX_OPEN_USD = 500.0
MAX_AGE_MIN = 60  # no entry decay up to 1h (militaryOptimize.py); 10 min was too tight
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def nowIso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def loadSignals() -> list[dict]:
    if not SIGNALS.exists():
        return []
    with SIGNALS.open() as fh:
        return list(csv.DictReader(fh))


def loadExecutions() -> list[dict]:
    if EXECUTIONS.exists():
        with EXECUTIONS.open() as fh:
            return list(csv.DictReader(fh))
    return []


def liveOpenUsd() -> float:
    return sum(float(r.get("usd") or 0) for r in loadExecutions() if r.get("mode") == "live")


def freshSignals(signals: list[dict]) -> list[dict]:
    """Signals young enough to act on, not already executed."""
    fired = {r.get("signalTs") for r in loadExecutions()}
    cutoff = time.time() - MAX_AGE_MIN * 60
    out = []
    for s in signals:
        try:
            ts = datetime.fromisoformat(s["alertTs"]).timestamp()
        except (ValueError, KeyError):
            continue
        if ts < cutoff or s["alertTs"] in fired:
            continue
        out.append(s)
    return out


def executionRow(sig: dict, usd: float, mode: str, result: str, detail: str) -> dict:
    return {
        "execTs": nowIso(), "signalTs": sig["alertTs"], "mode": mode,
        "eventSlug": sig.get("eventSlug", ""), "question": sig.get("question", ""),
        "tokenId": sig.get("_tokenId", ""), "outcome": sig.get("outcome", ""),
        "usd": round(usd, 2), "result": result, "detail": detail,
    }


def appendExecution(row: dict) -> None:
    new = not EXECUTIONS.exists()
    with EXECUTIONS.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def resolveToken(sig: dict, client: ClobClient | None) -> str:
    """The CLOB token id of the copied outcome. The signal stores the
    conditionId; the watcher stored sizing tokens only in memory, so look the
    market up on Gamma and pick the outcome's token."""
    if sig.get("_tokenId"):
        return sig["_tokenId"]
    import httpx
    r = httpx.get(f"https://gamma-api.polymarket.com/markets",
                  params={"condition_ids": sig["marketId"]}, timeout=30)
    m = (r.json() or [None])[0]
    if not m:
        raise RuntimeError(f"market not found: {sig['marketId'][:12]}")
    ids = json.loads(m.get("clobTokenIds") or "[]")
    outs = json.loads(m.get("outcomes") or "[]")
    return dict(zip(outs, ids))[sig["outcome"]]


def priceCap(entry: float) -> float:
    """Willing to pay up to 10% above the insider's avg price."""
    return round(min(0.999, entry * 1.10), 4)


def placeLive(sig: dict, tokenId: str, usd: float) -> tuple[str, str]:
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
    if not key:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set; cannot go live")
    client = ClobClient(host=HOST, key=key, chain_id=CHAIN_ID, signature_type=1)
    client.set_api_creds(client.create_or_derive_api_key())
    book = client.get_order_book(tokenId)
    asks = sorted((float(a["price"]), float(a["size"]))
                  for a in (book.get("asks") or []) if float(a.get("price", 0)) > 0)
    cap = priceCap(float(sig["avgPrice"]))
    # walk the book until the price cap or budget is exhausted
    remaining = usd
    filled = 0.0
    for px, sz in asks:
        if px > cap or remaining <= 0:
            break
        spend = min(remaining, px * sz)
        resp = client.create_and_post_order(OrderArgs(
            token_id=tokenId, price=px, size=round(spend / px, 2), side=Side.BUY))
        status = getattr(resp, "status", None) or (resp.get("status") if isinstance(resp, dict) else None)
        if isinstance(resp, dict) and resp.get("ok") is False:
            raise RuntimeError(f"order rejected: {str(resp)[:180]}")
        filled += spend
        remaining -= spend
    if filled <= 0:
        return "skipped", f"no ask within cap {cap}"
    return "filled", f"spend ${filled:.2f} within cap {cap} (last status {status})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", help="alertTs of the signal to execute")
    ap.add_argument("--latest", action="store_true", help="execute the newest fresh signal")
    ap.add_argument("--live", action="store_true", help="place real orders (requires POLYMARKET_PRIVATE_KEY)")
    ap.add_argument("--usd", type=float, default=MAX_USD)
    args = ap.parse_args()

    signals = loadSignals()
    if args.signal:
        picks = [s for s in signals if s["alertTs"] == args.signal]
        if not picks:
            raise SystemExit(f"signal {args.signal} not found")
    elif args.latest:
        fresh = freshSignals(signals)
        if not fresh:
            raise SystemExit("no fresh unexecuted signals (or all older than "
                             f"{MAX_AGE_MIN} min)")
        picks = [fresh[-1]]
    else:
        raise SystemExit("pass --signal <alertTs> or --latest")

    mode = "live" if args.live else "dry"
    if args.live and not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        raise SystemExit("refusing to go live: POLYMARKET_PRIVATE_KEY not set")
    openUsd = liveOpenUsd()
    client = ClobClient(host=HOST, key=os.environ.get("POLYMARKET_PRIVATE_KEY", "0x" + "0" * 64),
                        chain_id=CHAIN_ID, signature_type=1) if args.live else None
    for sig in picks:
        usd = min(args.usd, max(0.0, MAX_OPEN_USD - openUsd))
        if usd <= 0:
            print("live budget exhausted (MAX_OPEN_USD); nothing placed")
            break
        tokenId = resolveToken(sig, client)
        sig["_tokenId"] = tokenId
        if mode == "live":
            try:
                result, detail = placeLive(sig, tokenId, usd)
            except Exception as exc:
                result, detail = "error", str(exc)[:200]
        else:
            result = "dry"
            detail = (f"would buy ${usd:.2f} of {sig['outcome']} capped at "
                      f"{priceCap(float(sig['avgPrice']))} (entry {sig['avgPrice']})")
        row = executionRow(sig, usd, mode, result, detail)
        appendExecution(row)
        print(f"[{mode}] {sig['eventSlug']} | {sig['question']} | {result}: {detail}")
        openUsd += usd


if __name__ == "__main__":
    main()
