# Paper lanes: several parallel evidence books before the Nov 14 paper-gate readout

**PRE-REGISTRATION (this section written 2026-10-18, before any implementation ran or
produced data).** The lane-1 book alone cannot answer anything by Nov 14: it grades the
shipped military rule ($5k burst ≤0.35, fresh ≤3 mkts) at RESOLUTION, and most watched
markets resolve in Jan 2027 — status.md §6 expects ≥30 closed signals or 4 weeks, and
the 9-alert book has ~0 closes. `research/horizonExits.md` showed a marked exit fixes
the timing problem without losing the prediction: the T+7d mark correlates 0.851
(pearson) / 0.716 (spearman) with the resolution return in-sample, and the OOS failure
is already legible at T+1h/T+1d. This doc adds two more lanes so that by Nov 14 there
are several independent evidence books, not one slow one. Implementation notes are
appended at the end, clearly separated, after the build.

## Grading conventions (fixed FIRST, before any lane rule)

Everything below reuses the shipped lane-1 machinery verbatim; the only new object is
the *close convention* (a mark close instead of a resolution close):

- **Trigger/sizing conventions** — reused verbatim from liveWatcher + paperMarkToMarket:
  per (account, marketId, outcome) start-anchored 600s burst window with running-prefix
  threshold and running-average price (documented drift vs the research gap-chained
  frame in methodologyAttack.md A5 — every lane below carries that caveat); copy
  implementation = $100-capped (`spend = min(100, takeableShares × entry)`, shares =
  spend/entry), entry = alert bestAsk falling back to avgPrice.
- **Mark price** — Gamma `outcomePrices` of the copied outcome, exactly the
  paperMarkToMarket mark. **Sell slippage 50bps** on a mark exit (horizonExits.md
  convention): `exitValue = mark × (1 − 0.005)`, `pnl = shares × exitValue − spend`.
- **Resolution precedence** — if the market resolved before the close instant, the
  close is the resolution value (1.0/share won, 0.0 lost), no slippage
  (`closeType=resolution` vs `mark`). There are no prints after resolution to mark at.
- **Bookkeeping** — one signals CSV per lane (`data/live/signalsLane<N>.csv`, lane-1
  column shape), appended closes in `data/live/laneCloses.csv` with append-once
  idempotency key `(lane, horizon, alertTs, account, eventSlug)`, and daily open
  snapshots in `data/live/laneMarks.csv` with the trajectory idempotency key
  `(lane, date, alertTs, account, eventSlug)`. Close runs must be repeated-safe
  (paperPnl/paperTrajectory pattern).
- **winRate(lane)** = share of lane closes with `pnl > 0` (a close that resolved into a
  win counts as a win) — the horizonExits.md marked-exit winRate convention, not the
  resolution `won` share.
- **Freshness (A4 fix)** — no lane may state anything about an account it has not
  verified. Lane-2 rows inherit lane-1's gate (whose backfill-seen accounts already pass
  the one-time `/activity` rescue; push-tape-seen accounts still carry the watcher's
  first-observed-fill caveat, unchanged, same population as lane 1 by construction).
  Lane-3 accounts get a one-time `/activity` freshness window (5d pre-burst) recorded
  per row at alert time; lane 3 makes NO freshness gate, so the recorded flag is
  diagnostic, never load-bearing.

## Lane table

| lane | trigger | universe | sizing | close / grading | role by Nov 14 |
|---|---|---|---|---|---|
| 1 (existing) | military ≥$5k burst ≤0.35, fresh ≤5d(≈3d claim in docstring), ≤3 mkts Fees skipped | open military watch (1,335 mkt / 234 events) | $100 copy | resolution (paperPnl.py) — untouched | slow truth book |
| 2 (new) | IDENTICAL trigger to lane 1 — same alerts, same $100 copy | same as lane 1 (zero incremental exposure) | $100 copy (shared with lane 1) | **T+7d mark close** (+50bps sell slip, resolution precedence) | fast predictor book: every signal closes within 7 days |
| 3 (new) | bursts ≥$10k with burst-average price 0.55–0.90 on ANY (liquid, fee-free) market, no age/markets gate | bounded top-volume open markets, optional overlap with lane-1 mids (push tape covers them for bursts) | $100 copy, ≤3 new alerts/UTC-day | **T+3d and T+7d mark closes** (T+7d decision-grade) | short-horizon diagnostic book: post-burst continuation on live favorites |

### Why exactly these two (and nothing else)

- **Lane 2 is the horizonExits.md result put on a live book:** in-sample graded n=412,
  T+7d retMean +0.739, P(>0) 95.7%, win% 29.9 vs hold-to-resolution +1.222 — the mark
  calls resolution outcomes (corr 0.851) AND closes in days. Between the Oct 14 first
  signal and Nov 14 readout, lane 2 converts the resolution book's 0 closures into one
  close per alert. Nothing new is being claimed about the trigger: identical population
  to lane 1, so any lane-2 vs lane-1 divergence instruments the mark-vs-resolution
  agreement on live events.
- **Lane 3 tests the R11#1 (ideaGenAlpha.md (c) post-burst-continuation) family on live
  events where the burst tape is alive.** R3 (`oosFailureDiagnosis.md` Q1) showed the
  mark tell is a days-scale quantity (drift inside 24h already separates eras); R4
  (`favoriteBursts.md`) showed the favorite band is ~breakeven at resolution under
  delay-realistic pricing (HOLD $10k fav 0.55–0.85: ret +8.4% resolution, dr +9.4%,
  p5 −0.085..−0.084, win% 77–84) — i.e. the lane is NOT expected to carry copy alpha;
  its question is whether the live post-burst marks of $10k favorite bursts carry
  continuation signal worth grading further. The burst tape (≥$10k in 10 minutes) is
  where the information density is; grading at T+3d/T+7d is where the R3/R4 facts say
  the signal lives.
- **Rejected additions (do not re-litigate retired lines):** a fade lane is RETIRED —
  R3's Q2 fade PASS died under episode regrouping (methodologyChecks.md check #0: 30
  events → 9, top episode 108.8% of pool PnL, FAIL/ARTIFACT) and both sides of the
  fresh ≤0.35 burst die the same death; the longshot-family neighborhood fails on the
  fresh 200-slug holdout at every (burst-size × price) cell (favoriteBursts.md HOLD
  32/32 gradeable FAIL). No new evidence exists for either, so no second-grade lane
  rides them. $10k/≤0.40 lane-2 variant (in-sample T+7d PASS) also rejected: A3
  episode-composition shows the $10k family at the 0.80 bar with zero headroom and a
  −1.0 episode tail — nothing there to spend a lane on.

## Pre-registered gates (written before any lane data exists)

### LANE 2 gate (own gate, computed on laneCloses.csv horizon=7 rows only)

- Count clause first: the lane is gradeable when **≥8 closes exist by the Nov 14
  readout** (one close per lane-1 alert; lane 1 fired 9 alerts in 3 days, so ≥8 by
  Nov 14 is the realistic floor; fewer ⇒ **INCONCLUSIVE-THIN**, book keeps accruing,
  lane-1's original ≥30-close/4-week gate is untouched and remains the deciding lane-1
  evidence).
- **PASS** iff mean pnl per close ≥ **+$20** AND winRate ≥ **25%** — anchored to the
  in-sample T+7d expectation (retMean +0.739 ⇒ +$73.9 per $100 copy; win% 29.9), so
  PASS says the live tape prices like the in-sample regime and supports riding lane 1
  to resolution.
- **FAIL** iff mean pnl per close ≤ **−$27** OR winRate ≤ **15%** — anchored to the
  holdout T+7d expectation (retMean −0.274 ⇒ −$27.4 per copy; win% 15.3), so FAIL is
  the early, live confirmation that the OOS transport failure has gone live.
- Anything between the two zones ⇒ **INCONCLUSIVE** (keep accruing; no verdict, no
  tuning — the zone boundaries are not moved after data exists).
- Consequence wiring: lane 2's verdict is EVIDENCE ABOUT lane 1's future, never a rule
  change. Lane 1 keeps its own resolution gate regardless of lane 2's verdict; lane 2's
  verdict may raise or lower the operator's confidence in the lane-1 book before the
  full resolution sample exists, and says nothing else.

### LANE 3 gate (diagnostic; T+7d decision-grade, T+3d early-warning read only)

- Count clause: **≥20 T+7d closes** for any verdict (MIN_CELL = 20, the
  entrySweep/favoriteBursts pre-registered floor). At ≤3 alerts/day the lane likely
  reaches 15–20 closes by Nov 14; short of that ⇒ **INCONCLUSIVE-THIN**, book accrues.
- Universe caveat, stated as part of the gate: lane 3 fires on a **bounded
  top-volume open-market universe** (cap 600 markets across a broad tag set, fee-free
  markets only — favorites at ~breakeven edges cannot absorb fee drag, same reason the
  watcher skips feesEnabled markets) — this is a liquid-tape read, not the complete
  tape, and any future gate built on lane-3 data inherits that bias explicitly.
- Burst semantics caveat (A5, verbatim): lane 3 reuses the watcher's start-anchored
  600s running-prefix burst, NOT entrySweep's gap-chained window; the R4 expectations
  quoted above were graded on the gap-chained frame, so number-vs-number comparisons
  lane-3-vs-backtest carry that drift.
- **Diagnostic question (the reason the lane exists):** after a $10k burst at
  0.55–0.90, does the mark RISE or FALL away from the entry (post-burst-continuation
  vs mean-reversion) on current-era live events? R3 showed vote share is: OOS T+1d
  drift −13.6% mean / −7.5% median vs in-sample-era +20.7%/−18.9% — the sign is the
  thing being measured.
- **Kill rule (fixed now):** after ≥20 T+7d closes, if mean pnl per close ≤ $0 AND
  winRate ≤ 55% ⇒ the post-burst-continuation read is dead on live events ⇒ lane 3 is
  KILLED (config disabled), and no re-litigation without new evidence (same standard as
  the fade retirement).
- **Promotion signal (fixed now):** mean pnl per close > $0 AND winRate ≥ 65% AND n ≥
  20 ⇒ the family earns a graded (offline, entrySweep-frame) follow-up proposal;
  nothing moves to real orders from a paper lane in any case.
- Between ⇒ **INCONCLUSIVE**, keep accruing to 20 and re-read.

## Budget (fixed)

- Lane 2: $0 incremental notional (it re-grades lane 1's own $100 positions at a
  different horizon; nothing new at risk).
- Lane 3: $100 per copy, hard cap 3 new alerts per UTC day ⇒ **≤$300/day incremental
  at-risk paper**, written into config (`maxAlertsPerDay: 3`) and enforced in the
  watcher. The point is information, not PnL.
- Total book: lane 1 unchanged (≈$100/open signal), + ≤$300/day on lane 3 early life.

## Operations (fixed)

- Implementation is strictly additive to `scripts/liveWatcher.py` via a separated
  module (`scripts/paperLanes.py`) imported by the watcher; with
  `configs/paperLanes.yaml` absent or lanes disabled, lane-1 behavior is byte-identical
  (same constants, same state keys, same CSVs, same log lines).
- Mark/close runs: `scripts/paperLaneMarks.py` (new), safe to run repeatedly; the
  operator wires it into dailyCatchup.sh (block provided at the end of the run report;
  the investigators do not touch cron or dailyCatchup.sh).
- Restarts: relaunch with the same nohup convention dailyCatchup uses; state.json
  survives (lane keys are additive), watermarks untouched.
- All lane history lives under `data/live/` in NEW files only; tests run on tmp dirs,
  never the live CSVs.

## Results (appended after implementation + relaunch)

Appended below after the build/relaunch.

## Implementation notes (appended after the build + relaunch)

Built and relaunched 2026-10-17. Files:

- `configs/paperLanes.yaml` — the lane params above (budget caps included:
  lane3 `maxAlertsPerDay: 3` ⇒ ≤$300/day incremental paper). File absent,
  malformed, or a lane set `enabled: false` ⇒ that lane's hooks are no-ops
  and lane-1 behavior is byte-identical.
- `scripts/paperLanes.py` (new, imported by liveWatcher) — lane engine:
  lane-2 clone of every lane-1 alert (fired inside `alert()` after the
  lane-1 CSV write; shares lane-1's dedup key, so exactly one row per
  alert); lane-3 burst engine, top-volume universe refresh (Gamma events by
  volume over the configured tag set, cap 600, cached to
  `data/live/eventsLane3.json`, TTL 300s), and the gap-rescue poll. Semantics
  are reused verbatim from the watcher (start-anchored 600s running-prefix
  bursts per A5, same /v2/trades walk with only the filter amount changed):
  helpers (`fillKey`/`bookSize`/`normalizeV2Trade`) are supplied by
  liveWatcher and passed in, not forked. Two deliberate deviations,
  documented in the module docstring: the lane-3 fill dedup store is
  lane-LOCAL (a shared store would let lane-3 rows consume lane-1's SEEN
  bookkeeping, breaking byte-identical lane-1 behavior), and lane 3 keeps
  NO age gate — the `/activity` freshness stamp (A4 fix, mirrors
  `verifyAccountAge`) is recorded per row as `ageStamp`/`freshWindow5d`,
  diagnostic, never load-bearing.
- `scripts/paperLaneMarks.py` (new) — mark-close bookkeeping. Sizing reuses
  `paperMarkToMarket.copySpend` verbatim ($100-capped at bestAsk, avgPrice
  fallback). A close is a MARK exit at T+H (`gamma outcomePrices × (1 −
  50bps)`); resolution precedence when the market resolved before the close
  instant (1.0/0.0 per share, `closeType=resolution`). Outputs:
  `data/live/laneCloses.csv` (append-once key
  `(lane, horizon, alertTs, account, eventSlug)`) and
  `data/live/laneMarks.csv` (daily snapshots, trajectory key
  `(lane, date, alertTs, account, eventSlug)`). Prints realized P&L plus the
  pre-registered lane-2 gate and lane-3 kill/promotion verdicts (thresholds
  are module constants pinned to the doc). `--report` prints gates only.
- `scripts/liveWatcher.py` — additive edits ONLY: module import +
  `LANES` config carrier (None until `main()`), lane-2 hook at the tail of
  `alert()`, lane-3 universe refresh/poll/drain hooks in `main()`, and the
  tape subscription mid-set extended by `holder["lane3"]` when lane 3 runs.
  No lane-1 logic, constant, or state key changed.
- Tests: `tests/test_paperLanes.py` (12) + `tests/test_paperLaneMarks.py`
  (13) — config parsing/fallback defaults, lane-1 constants + alert-path
  byte-identity with lanes off, burst firing/dedup/window-reset/daily
  budget cap/price band/fee skip, poll watermark idempotency, cache
  short-circuit, slippage + resolution-precedence accounting, idempotent
  close/snapshot appends on tmp roots (never the live CSVs). `uv run
  pytest`: **175 passed** (150 baseline + 25 new). `ruff check` on the new
  files is clean except the blind-exception catches mirrored from the
  watcher's own established pattern.
- Live relaunch: PID 942 (+uv wrapper 859) killed; relaunched with the exact
  dailyCatchup convention
  (`nohup uv run python scripts/liveWatcher.py >> logs/liveWatcher.log`).
  Verification: process up (46057/46060); `watching 1335 open military
  markets (234 events)` unchanged (lane-1 coverage identical); new line
  `lane3 watching 616 open markets (10 volume events)`; state.json gains
  only `state["lane3"]` (616 watermarks, alerts list, daily counter) with
  lane-1 keys byte-identical (accounts/lastTs/alerts untouched;
  pre-restart file backed up to /tmp/state.backup.paperLanes.json).
  First lane-3 signals fired within the initial `/v2/trades` backfill: 3
  bursts on `who-will-be-the-next-prime-minister-of-israel...` at burst
  averages 0.6365/0.6635/0.680 (all inside the 0.55–0.90 band, ≥$10k in the
  600s window; observed fill No side), recorded with `ageStamp=verified`
  and mixed `freshWindow5d` flags — the daily cap engaged at 3/3 for
  2026-10-17 and suppressed a 4th burst, proving the budget enforcement
  live. `data/live/signalsLane2.csv` is created on the next lane-1 alert
  (no lane-1 alert fired in the relaunch window; its history-clone row
  logic is covered by tests). One live bug was caught and fixed during the
  relaunch: httpx `Client.get` takes `params` keyword-only — the three
  direct `.get(url, {...})` calls in the new module now pass `params=`, and
  a MockTransport smoke pins the signature. The daily mark run is
  operator-wired (block below; not wired by the build).
