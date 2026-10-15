"""RTDS push-tape client for liveWatcher: streams trades over the websocket
at wss://ws-live-data.polymarket.com instead of polling the Data API.

Protocol (verified live 2026-10-09):
  subscribe: {"action": "subscribe",
              "subscriptions": [{"topic": "activity", "type": "*"}]}
  - verified live: type "*" WITHOUT a filters key streams the global tape.
    Odd server behavior: {"type": "trades"} acks but delivers nothing unless
    "filters": "" is present; "filters": "" on type "*" also delivers
    nothing. Bare {"topic", "type": "*"} is the shape that works.
  - each accepted subscription is acked with one empty frame.
  - the unfiltered global tape streams all trades; we filter client-side by
    condition id.
  envelope:  {"topic": "activity", "type": "trades|orders_matched",
              "timestamp": <ms>, "payload": {...}}
  payload:   proxyWallet, side, size, price, outcome, conditionId, eventSlug,
             slug, transactionHash, timestamp (SECONDS — envelope is ms).

The client runs in a daemon thread, reconnects with capped backoff, and calls
onRow(row, backfill) where row matches the Data-API row shape evaluate()
already consumes:

  {"mid": <conditionId>, "ts": <sec>, "proxyWallet": ..., "side": ...,
   "size": ..., "price": ..., "outcome": ..., "txnHash": ...}

Rows whose mid is not in the mids() set are dropped before the callback.

Run standalone to probe the tape:
  uv run python scripts/rtdsTape.py [seconds]
"""

import json
import threading
import time

from websockets.sync.client import connect

RTDS_URL = "wss://ws-live-data.polymarket.com"
TOPIC = "activity"
IDLE_TIMEOUT = 30.0
BACKOFF_MAX = 60.0


class RtdsTape(threading.Thread):
    """Background websocket reader; onRow(row, backfill) is called from this
    thread (the watcher must queue or lock around it)."""

    daemon = True

    def __init__(self, mids, onRow):
        super().__init__(name="rtds-tape")
        self.mids = mids                  # () -> set[str] of condition ids, or None for all
        self.onRow = onRow                # (row: dict, backfill: bool) -> None
        self._stop = threading.Event()
        self.connected = threading.Event()
        self.lastMsgTs = 0.0

    def stop(self) -> None:
        self._stop.set()

    def _normalize(self, msg: dict) -> dict | None:
        if msg.get("topic") != TOPIC or not isinstance(msg.get("payload"), dict):
            return None
        p = msg["payload"]
        mid = str(p.get("conditionId") or "")
        wallet = str(p.get("proxyWallet") or "").lower()
        ts = int(p.get("timestamp") or 0)
        if not mid or not wallet or ts <= 0:
            return None
        # envelope timestamp is ms; payload timestamp is seconds
        if ts > 10**12:
            ts //= 1000
        return {"mid": mid, "ts": ts,
                "proxyWallet": wallet,
                "side": str(p.get("side") or "").upper(),
                "size": float(p.get("size") or 0),
                "price": float(p.get("price") or 0),
                "outcome": str(p.get("outcome") or "?"),
                "txnHash": str(p.get("transactionHash") or ""),
                "eventSlug": str(p.get("eventSlug") or "")}

    def run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with connect(RTDS_URL, ping_interval=20, ping_timeout=20,
                             close_timeout=5) as ws:
                    ws.send(json.dumps({"action": "subscribe", "subscriptions": [
                        {"topic": TOPIC, "type": "*"}]}))
                    print("[rtds] subscribed to global activity/trades tape", flush=True)
                    self.connected.set()
                    backoff = 1.0
                    while not self._stop.is_set():
                        raw = ws.recv(timeout=IDLE_TIMEOUT)
                        self.lastMsgTs = time.time()
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        if not raw.strip():  # empty ack frame
                            continue
                        try:
                            msg = json.loads(raw)
                        except (ValueError, TypeError):
                            continue
                        row = self._normalize(msg)
                        if row and (self.mids is None or row["mid"] in self.mids()):
                            self.onRow(row, False)
            except TimeoutError:
                # stale connection: no message in IDLE_TIMEOUT, force reconnect
                print("[rtds] idle timeout, reconnecting", flush=True)
            except Exception as exc:
                if self._stop.is_set():
                    break
                print(f"[rtds] connection error: {exc}", flush=True)
            self.connected.clear()
            if not self._stop.is_set():
                time.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="probe the RTDS trades tape")
    ap.add_argument("seconds", nargs="?", type=int, default=60)
    args = ap.parse_args()

    shown = 0

    def onRow(row, backfill):
        nonlocal shown
        shown += 1
        print(f"{row['ts']} {row['proxyWallet'][:10]} {row['side']} "
              f"${row['size'] * row['price']:,.0f} @ {row['price']:.3f} "
              f"{row['outcome']} mid={row['mid'][:12]} {row['eventSlug'][:40]}")

    tape = RtdsTape(None, onRow)  # no mid filter: show the raw tape
    tape.start()
    time.sleep(args.seconds)
    tape.stop()
    print(f"{shown} rows in {args.seconds}s")


if __name__ == "__main__":
    main()
