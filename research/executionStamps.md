# Execution stamps: the paper↔real-execution bridge, measured per lane

**PRE-REGISTERED 2026-10-17 (before any stamp implementation ran or produced data).**
Motivation: engineParity's `notExecutedLegalPrefix` shows 24/427 in-sample alerts whose
delayed copies never landed; OOS `landed300` is 49.8% (§9.3) / 68.8% (§9.4) across OOS
pulls; R17 measured sibling liquidity vanishing 15–30 min around triggers. The paper
lanes grade $100 copies at entry = alert-time bestAsk — but nothing records whether the
market actually offered a fillable book at/near that ask later. Stamps close that gap
with live CLOB data, per alert lane, at two fixed horizons.

## Measurement object (fixed FIRST)

For every alert in every lane's signals file (lane 1 `data/live/signals.csv`,
lane 2 `data/live/signalsLane2.csv`, lane 3 `data/live/signalsLane3.csv`):

- **T0 book state** = what the alert row already records, written by the watcher at
  burst/alert time: `bestAsk` (fallback `avgPrice`), `askSize`, `takeableShares`.
  We do NOT re-derive T0; the row is the T0 snapshot. (A5 note: the watcher's
  `takeableShares` sums asks ≤ 1.1× burst-average price — burst-window semantics, not
  an entrySweep frame. Stamps do not relitigate: see threshold below.)
- **Stamp semantics** (measured at stamp time, from the CLOB `/book` at
  `clob.polymarket.com/book?token_id=<copied-outcome token>`):
  - `t0Ask` = row's `bestAsk`, fallback `avgPrice` — the reference price for the floor.
  - `askNow`, `bidNow`, `askSize` = live best ask / best bid / size at best ask.
  - `spreadPct` = (askNow−bidNow)/askNow×100 when both sides exist, else empty.
  - `takeableUsd150` = Σ size×price over ask levels priced ≤ **1.5×t0Ask** — i.e. the
    USD depth within a 50% floor of the alert ask ("can you still fill $100 without
    repricing >50%").
  - `takeableUsd0` = same sum restricted to ≤ t0Ask ("fill $100 at the T0 price or
    better", strictest reading). Both columns are stored; the pre-registered headline
    fill predicate is `fill100 = takeableUsd150 ≥ 100`.
  Both sums assume zero impact at quoted sizes (limit-order depth, no walk penalty) —
  a conservative upper bound on takeable value.
- **missReason** enum (exactly one, created on every terminal stamp):
  | value | definition |
  |---|---|
  | `ok` | book pulled, askNow ≤ 1.5×t0Ask, values recorded |
  | `ask-gt-1.5x` | askNow exists but > 1.5×t0Ask (takeable sums = 0; the priced floor is gone) |
  | `book-empty` | book pulled, asks empty, bids present (no offer to take) |
  | `book-closed` | both sides empty AND gamma reports the market closed/resolved |
  | `dead-market` | both sides empty, market open, no quotes (book-closed's open twin) |
  | `api-error` | retries exhausted — see retry rule; left unstamped within the grace window |
- **`suspect` (dataQuality)** = `no-prints-never`: when the book is unusable
  (book-empty / dead-market / book-closed), `clob /last-trade-price` is probed; a 404
  or price ≤ 0 marks the market as having no prints ever — such stamps are
  low-evidence and consumers should exclude them from fill-rate denominators.
- **Horizons**: `300` and `600` seconds after `alertTs`. Stamps at the first
  dailyCatchup tick after T+300s and again after T+600s. One stamp row per
  (lane, horizon, alertTs, account, eventSlug) — duplicated events share the key by
  construction, each horizon stamped at most once, per the laneMarks idempotency
  pattern.
- **`stampTs` + `stampDrivenS`**: stampTs = wall clock at measurement; stampDrivenS =
  stampTs − (alertTs + horizon). The 10-min catchup cadence means stampDrivenS ∈
  [3s, ~610s] in practice (first tick after each horizon: average ≈ 300s of slippage,
  worst ≈ 600s since the T+600 tick can coincide with the T+300 tick on a 600s-spaced
  schedule, but is never *later* than the first tick after T+600). The claimed "≤5 min
  average slippage" holds on average, not per-row — the per-row value is `stampDrivenS`,
  always on the record. Group-level reads must bucket by stampDrivenS.
- **Retry rule**: `getWithRetry`, 3 attempts, 1/2/4s backoff (watcher pattern). A
  transport failure inside the first hour after the horizon (stampDrivenS ≤ 3600) is
  left UNstamped so the next tick re-measures; beyond that it is stamped `api-error`
  (terminal, prevents permanent holes). One bad row never blocks the sweep.
- **Output**: `data/live/execStamps.csv`, header created on first append, one line per
  terminal stamp; a run that is interrupted never rewrites the file — append-only,
  idempotent skip by key, per paperTrajectory/paperLaneMarks conventions.
- **Runtime budget**: ≤ 60 stamps per pass (cap), remainder re-measured next tick —
  keeps every pass inside the dailyCatchup fast-lane budget.
- **Read-only contract**: the watcher runs continuously; this script reads
  signals/events caches and never writes to any watcher-owned file (events caches are
  read, gamma lookups for missing tokens go straight to the API, not into the caches).

## Wiring (decided at build time, after the script exists)

Unconditional fail-soft run each tick. dailyCatchup.sh's *report block* runs once per
day (marker `logs/lastDailyReport`), so wiring inside it would push stampDrivenS to
hours/24h and break the cadence pre-registration above. The stamp line therefore rides
the always-run self-heal section of dailyCatchup.sh (the script itself is already cron'd
*/10 — no crontab change). One appended line, after paperLaneMarks.py's section,
logging into logs/dailyReport.log. Exact block recorded in the implementation notes
below once the live pass confirms the script is fast (<20s) and fails soft.

---

## Implementation notes (appended AFTER the build — not pre-registration)

- `scripts/bookExecStamps.py` — standalone, no watcher imports; identical CLOB
  access pattern to liveWatcher (`/book?token_id=`, httpx, `getWithRetry`
  3 attempts 1/2/4s backoff) with token ids resolved from the watcher's own
  events caches read-only (`events.json` for lane 1/2, `eventsLane3.json` for
  lane 3; cache misses go straight to gamma `/markets?condition_ids=`, never
  back into the watcher's cache files). Due selection: every signal row older
  than `alertTs+300s` / `+600s` without a stamp key gets a pull; unresolvable
  tokens are left unstamped for the next tick, transport failures inside the
  1h grace window likewise (after grace → terminal `api-error` row). Cap 60
  stamps/pass bounds every tick; a capped run flushes what it has first.
- `data/live/execStamps.csv` row shape: lane, horizon, alertTs, account,
  eventSlug, outcome, tokenId, t0Ask, stampTs, stampDrivenS, askNow, bidNow,
  askSize, spreadPct, takeableUsd0, takeableUsd150, fill100, missReason,
  suspect. Append-once by the pre-registered key; header on first write.
- Wiring (verified fast + fail-soft, one appended line): the dailyCatchup.sh
  *report block* is marker-gated to once per UTC day, so it cannot serve the
  T+300/T+600 tick mechanics without pushing stampDrivenS to hours; the line
  rides the always-run section instead (no crontab change, same */10 cadence):

```sh
# 2. Exec-fill stamps: CLOB book at T+300s/T+600s for every lane's alerts
#    (research/executionStamps.md; rides the every-tick cadence, not the
#    once-a-day report block, per the pre-registered stampDrivenS semantics).
uv run python scripts/bookExecStamps.py >> logs/dailyReport.log 2>&1
```

- Tests: `tests/test_bookExecStamps.py` (8) — idempotency, both-horizon due
  windows with stampDrivenS checks, full missReason enum coverage (ok /
  book-empty / dead-market+no-prints-never / book-closed / ask-gt-1.5x /
  api-error grace-then-terminal), $100-takeable predicate (boundary:
  $60 depth → fill100 False), fail-soft on missing/corrupt inputs, gamma
  fallback on a cache miss, run-cap handoff across ticks. MockTransport
  throughout; `params` keyword-only respected (R14).
- Full suite: `uv run pytest` → **196 passed** (188 pre-existing + 8 new).
  `ruff check` clean on both new files (blind-exception catches kept with
  `# noqa: BLE001` + rationale, mirrored from the watcher's established
  pattern — paperLaneMarks/codebase carry the same style).
- Live verification 2026-10-17 20:20 UTC (watcher untouched, PID 46057):
  first pass stamped **22** (lane1=18, lane3=4; all missReason=ok, driven
  ≈ 246728/246428 s for the Oct-14 alerts and ≈ 4400 s for today's lane-3
  alerts) in 2.8 s; takeableUsd150 for the invade-iran alert showed $51.8k
  within the 1.5× floor at ask 0.16 (T0 ask 0.17) while the israel-PM Yes
  ask had drifted 0.26 → 0.29 with $119k takeable under 0.39. Second pass
  immediately after: `execStamps: nothing due`, file byte-unchanged
  (idempotent). signalsLane2.csv did not exist yet (no lane-1 alert since
  the lane-2 relaunch); the wiring created no lane-2 stamps and stayed
  silent on that lane — fail-soft as pre-registered.
