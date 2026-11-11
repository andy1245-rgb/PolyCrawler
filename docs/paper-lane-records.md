# Paper-lane records — event time, book shape, and signal identity

> What the paper-lane books record, why `alertTs` and `writtenTs` are two different columns,
> how a position's horizon is anchored, what the backtester does with a missing price, and how
> the CSV books stay readable across a schema change. Ends with what is still contaminated in
> the live books and the rebuild that would clear it.

A live signal has two times: when the event happened and when the watcher noticed. The books
recorded one, and every consumer read it as the other. Fixing that meant fixing the readers
that measure elapsed time from it, which is the larger half of the work. Three further defects
were found on the way — a skipped trade that left no trace, a schema change that would have
misaligned existing books, and a dedupe key that had already collapsed 72 rows to 22.

## 1. `writtenTs`, and `alertTs` now means the event

**The defect.** `alertTs` was written as `nowIso()`, the wall clock at the moment of writing.
Every consumer already treated that column as the event time: `bookExecStamps` computes
`dueAt = alertTs + horizon`, `paperLaneMarks` computes T+3d/T+7d from it, `laneWeekly` reads its
dates from it, `execute.py` uses it as the signal id. The event timestamp was not lost lower down
the pipe. It was never written at all, and the column meant to hold it held the write time.

Evidence, reproduced as a test before the fix:

```
console: *** SIGNAL 10-28 10:37 0xw e-slug        <- the event
csv row: alertTs = 2026-11-10 08:54:49            <- the write
```

**The change.**

- `scripts/liveWatcher.py`: `SIGNAL_FIELDNAMES` is the 13 alert fields plus `writtenTs`. `alert()`
  formats the event time from `ts` into `alertTs`, records `nowIso()` in `writtenTs` once, and
  passes both to lane 2.
- `scripts/paperLanes.py`: `L2_FIELDNAMES` and `L3_FIELDNAMES` gain `writtenTs` as the last
  column. `onAlert1` takes `eventTs` and `writtenTs` instead of a single `when`. `alert3` writes
  the event time into `alertTs` and `nowIso()` into `writtenTs`.

A replayed burst now carries the day it happened in `alertTs` and the day it was noticed in
`writtenTs`, and the gap between them is the lateness.

## 2. Readers that measure elapsed time need `writtenTs`

Moving `alertTs` to the event time silently re-anchored every horizon consumer, because until now
the two meanings coincided. `paperLaneMarks` closes a position once `now >= alertTs + horizon`,
which was correct only while `alertTs` was the detection time. Under the new semantics a burst
that happened 10 days ago is already past T+3d and T+7d the moment the row exists, so it closes
on the first pass, at detection-day price, and is written into `laneCloses.csv` as a T+7d mark.
That price would then feed the pre-registered [`0.55, 0.85)` gate in `research/paperLanes.md`,
which is anchored on real T+7d marks, for exactly the replayed population this change is about.

So T+0 of a paper position is explicitly the detection moment:

- `scripts/paperLaneMarks.py:entryTs(row)` returns `writtenTs` when the book records it and falls
  back to `alertTs` on books written before the column existed. Horizon closes and the open
  snapshot both use it. `alertTs` still keys `laneCloses.csv`, because it is the alert's identity.
- `scripts/paperMarkToMarket.py` takes its weeks-since-first-signal from `writtenTs` for the same
  reason: that gate counts how long the book has been observed, not how old the oldest event is.

Two consumers deliberately stay on `alertTs` (the event time):

- `bookExecStamps.py` keeps `dueAt = alertTs + horizon`. This looks like a regression and is not:
  `research/executionStamps.md` buckets only rows whose `stampDrivenS <= 3600`. Anchoring on the
  event time pushes a replay to roughly `10^6` s, so the documented filter now excludes it. The old
  behaviour put 60 fabricated stamps inside the pre-registered `[3, 610]` window, which is the
  corruption this change exists to stop.
- `execute.py` keeps its 60-minute age gate on `alertTs`, so a burst replayed days late is no
  longer executable. That closes a real hole: before this, a replayed alert looked fresh to
  `--latest` and could have been bought. It is a behaviour change in the only path that can place
  real orders, and it is recorded here rather than inherited silently.

## 3. A missing price is counted, not dropped

**The defect.** `_onBuy` ended with `if shares <= 0 or ourPrice is None: return`. With no print
inside the 6h staleness window there was no price, no trade, and no record that a copy had been
attempted, so a run that skipped half its opportunities looked identical to one that took them
all.

**The change**, in `src/polycrawler/backtest.py`:

- `Book.noPrice` counts three things, named for their units because they differ:
  `entryAttempts` and `exitAttempts` count fill rows that wanted a price, `markLots` counts
  positions marked without one.
- `summary.json` carries `noPriceSkips` and `entryCoverage`, which is
  `tradeCount / (tradeCount + entryAttempts)`, or `null` when nothing was attempted.
- `formatSummary` prints both, formatted like its neighbours.
- `runRolling` sums the window counters and recomputes coverage from the sums rather than averaging
  window ratios.

No behaviour changed. `orderShares` already returned `0.0` for a null price and `_maybeExit` could
already not exit an unarmed key, so splitting both conditions only adds the counters. An idle row
blocked by a cap rather than by price still lands in neither counter, so coverage reads "of the
copies a run tried to price, how many had a price".

## 4. The schema guard, because `data/live` cannot be rebuilt yet

The three existing books have 13, 13 and 15 column headers with no `writtenTs`. Appending a 14 or
16 column row would misalign every downstream reader silently.

`appendCsv` reads the header already on disk and writes each row in that header's own order, by
name. A legacy book keeps its shape and the process prints one line per book:

```
[2026-11-10 08:56:24] signals.csv predates writtenTs; rows stay in its 13-column
                      shape until the book is rebuilt
```

Hardened after review, each pinned by a test that fails if the line is reverted:

| Case | Behaviour |
|---|---|
| zero-byte file | treated as no header, so header and first row are written |
| blank first line | same, so a half-written file heals instead of appending blank lines forever |
| non-UTF-8 book | `ValueError` caught with `OSError`/`csv.Error`, so the writer cannot kill the watcher |
| short or long row | fitted by name to the header width, never written raw |
| reordered or superset header | values land under their own names, unknown columns left blank |

The `ValueError` case matters: `alert()` calls `appendCsv` on every alert and nothing upstream
catches, so before that fix a book in another encoding would have crashed the watcher and recursed
on every restart.

**Consequence to hold in mind:** on the existing books `writtenTs` is withheld, so the `alertTs`
correction is the whole of the protection there, and `entryTs` falls back to `alertTs` exactly as
before. That keeps the current books behaving as they always did. It does not tell a reader from
the file which historical rows were replays. Only the rebuild does that.

## 5. The dedupe key, which was already losing alerts

`paperPnl.py` and `paperMarkToMarket.py` decided which signals they had already handled by a set of
`alertTs` alone. That key has already collapsed the book: `signals.csv` holds 72 rows with only
**22 distinct `alertTs` values**, 59 of the 72 share a second with another alert, and three
different accounts share `2026-10-14 23:43:40`. `paperPnl.csv` has never existed so nothing has
been lost yet, but the moment it appears both scripts would see 22 of 72 and skip the other 50
without a word.

Event timestamps cluster harder than write timestamps, so this change would have made it worse.
Both now key on `signalKey(row)` = `(alertTs, account, eventSlug)`, the tuple `bookExecStamps`,
`laneWeekly` and `paperLaneMarks` already use. No migration: `paperPnl.csv` does not exist and
`openPositions.csv` is rewritten wholesale each run.

## 6. Review: what an independent read of the change caught

An independent read-through of the diff against the repository found one thing that mattered,
which is section 2: the horizon consumers. Its verdict on that ground was that the change was not
safe to commit, and that was correct. What it got right in the small is listed in section 7 as
tests that now fail on revert.

Where the review and the change disagreed, and how each was resolved:

- It called the `bookExecStamps` re-anchor a regression. It is the opposite: the pre-registered
  filter is `stampDrivenS <= 3600`, and event-anchoring is what makes a replay fall outside it.
  That reasoning is in section 2.
- It flagged `execute.py` refusing late alerts as an undocumented side effect. Agreed on
  documentation, which section 2 now carries. The behaviour is the safe one and was kept.
- It read "62 of 72 rows carry 2026-11-09" as the premise. It is 62 rows dated 2026-11-09 of which
  61 are replayed, confirmed by matching the watcher's console event times against the rows.
- Its note that a bare commit would record only the file-mode change was true when it looked; the
  work is committed with explicit pathspecs.

`noPriceSkips` keys were renamed to `entryAttempts`/`exitAttempts`/`markLots` because the review was
right that one dict was mixing three units. `formatSummary` formatting was fixed.

## 7. Verification

Both spellings give the same result:

```
.venv/bin/python -m pytest -q   ->  212 passed
uv run pytest -q                ->  212 passed
```

The tree carried 1 failed and 195 passed before this work. 16 tests were added and the one
pre-existing failure was repaired, so the suite is green: 196 tests existed before, 212 exist now.

The failure was `test_order_burst_onchain.py::test_sample_days_deterministic_and_sorted`, which
asserted `len(days) == 34 * 2` against a comment dating the range "Jan 2024 .. Oct 2026".
`sampleDays` walks from its start month to the current month, so the count advances every month and
the literal went stale: in Nov 2026 the walk covers 35 months and returns 70. The expected count is
now derived from the span the sampler actually walks, using a closed-form `monthSpan` rather than a
copy of the loop so an off-by-one inside `sampleDays` cannot mirror itself in the expectation, and
the clock is sampled either side of the call so a month boundary mid-test cannot flake it. That
test's `d.year <= 2026` bound, which would have rotted the same way in January, is replaced by
asserting the walk starts at the given month and ends at the current one. It was not introduced
here, but it blocked a green suite.

New tests, and each one is checked to fail when the fix it guards is reverted:

| Test | Pins |
|---|---|
| `test_paperLanes::test_replayed_alert_keeps_its_event_time` | a replayed burst keeps its own date in `alertTs`, differs from `writtenTs`, lane 2 mirrors both |
| `test_paperLanes::test_legacy_signal_header_keeps_rows_aligned` | a pre-`writtenTs` book gets a row of its own width; a fresh book gets the full header |
| `test_paperLanes::test_blank_first_line_is_not_a_legacy_book` | a half-written book heals |
| `test_paperLanes::test_undecodable_book_does_not_raise` | a foreign encoding cannot kill the watcher |
| `test_paperLanes::test_short_row_cannot_misalign_a_current_book` | a short row is fitted, not written raw |
| `test_paperLanes::test_row_maps_by_name_not_by_position` | a reordered header maps by name |
| `test_paperLaneMarks::test_horizon_runs_from_detection_not_from_the_event` | a burst detected today does not close T+7d today |
| `test_paperLaneMarks::test_horizon_closes_once_detection_is_old_enough` | it does close once detection is 10 days old |
| `test_backtest::test_noPriceSkipIsCountedAndCoverageReported` | no price means one entry skip, coverage 0.0, visible in `formatSummary` |
| `test_backtest::test_entryCoverageIsCompleteWhenEveryCopyIsPriced` | priced runs report zero skips, coverage 1.0 |
| `test_backtest::test_noPriceCountersSurviveAnEmptyRun` | counters exist, coverage `null` when nothing was attempted |
| `test_backtest::test_unpricedExitIsCountedAndTheLotSurvives` | an unpriced exit is counted and the lot stays open |
| `test_backtest::test_unarmedKeyStillCannotExit` | the split did not let an unarmed key exit |
| `test_backtest::test_markWithoutAPriceIsCounted` | an unpriced mark is counted |
| `test_paper_mark_to_market::test_signalKey_keeps_apart_alerts_sharing_a_second` | two alerts in one second are two alerts |
| `test_paper_mark_to_market::test_paperPnl_keys_signals_identically` | the two scripts cannot drift apart on identity |

Mutation-checked rather than assumed: commenting out each of the three `noPrice` increments fails
three tests; reverting `entryTs` to `parseAlertTs(row["alertTs"])` fails the horizon test; removing
the `ValueError` catch, the `or None` on the header, or the by-name fit each fails its own test;
and making `sampleDays` stop a month early or take one sample instead of `perMonth` fails the span
test, so the derived count is not vacuous. The pre-existing
`test_lane2_clone_writes_identical_shape`, which pins the lane-1 header to `L2_FIELDNAMES`, still
passes, so the two writers cannot drift.

Also verified by hand against copies of the three real headers: signals 13 columns, lane2 13, lane3
15, every row aligned, `data/live` untouched.

## 8. What is not verified

- The live path is verified by the repo's tests and by a smoke test of the writer against copies of
  the real headers. No live alert has yet been written by the new code: the deployed watcher
  process is the old one.
- `entryCoverage` is exercised on synthetic frames only. No `pc2 backtest` ran on real data with
  this change, so the coverage of existing runs is unknown. It will be in every summary from now
  on.
- The `exitAttempts` and `markLots` counters are covered by direct unit tests of `_maybeExit` and
  `_markOpen`, not by a full replay. A full-replay case for either is not in the suite.
- Lane 2 cloning into a still-legacy book is covered by composition, not by its own test: the guard
  is tested against all three real headers and against reordered, short and blank books, and the
  clone path is tested against a fresh book.
- Nothing enforces a single writer. `appendCsv` owns the write in code, but `readHeader` plus
  `open("a")` is a TOCTOU: two processes that both see a missing file would both write a header. It
  did not fire under 4x3 racing processes, and `dailyCatchup.sh` only restarts the watcher when
  `pgrep` finds none.
- The `bookExecStamps` upper lateness bound is still missing. Replays now fall outside the
  documented filter instead of inside it, but they are still written. Recommended next: skip a
  stamp whose `stampDrivenS` exceeds a configurable ceiling and count it as `stale` instead.

## 9. The replay, and what in the live books is trustworthy — 2026-11-10

The deployed watcher is still the process cron started at 2026-11-09 15:00:01 (pid 1074445), so it
holds the pre-change code. `writtenTs` will not appear and `alertTs` will stay write-time until
that process next starts. It was not restarted mid-burst, and cron restarts it on the next tick
where it finds it down.

The replay itself is over (the dedup keys are in `state.json`), so nothing is being contaminated
now. The same replay would happen on any cold start with an empty dedup store; this change makes it
visible rather than silent, and section 2 keeps its horizon damage out of the gates, but it does
not prevent the replay.

Reconstructed from `logs/liveWatcher.log` by matching console lines, which record the event time,
against the CSV rows, which record the write time:

| Book | Rows | Untrustworthy | Why |
|---|---|---|---|
| `signals.csv` | 72 | **62** | all rows dated `2026-11-09`; 61 are replayed bursts from 10-18 to 11-05 and 1 is genuinely fresh, and the file cannot tell you which |
| `signalsLane2.csv` | 63 | **62** | mirrors lane 1 |
| `signalsLane3.csv` | 6 | **3** | all three replayed, events from 10-18 and 10-22 |
| `execStamps.csv` | 252 | **226** | keyed to an `alertTs` of `2026-11-09`, so 226 of 252 `stampDrivenS` rows inherit the fabricated timestamp; 124 of 252 still land inside the pre-registered `[3, 610]`s window |

**Trustworthy:** the 10 rows in `signals.csv` dated 10-14 to 10-17, the 1 row in `signalsLane2.csv`
dated 10-17, the 3 rows in `signalsLane3.csv` dated 10-17, and the 26 `execStamps` rows keyed to
those dates. They were written live, seconds after the event.

**Nothing derived from the 2026-11-09 rows should be quoted:** `laneCloses.csv`, `laneMarks.csv`,
`openPositions.csv`, `trajectory.csv` and the lane readout all read those books. The lane gates are
`INCONCLUSIVE-THIN` anyway, but that is beside the point here.

## 10. The rebuild, which has not been run

This is the sequence that would put `data/live` on the clean shape. It is destructive in two ways:
it removes 127 rows, and it re-runs the derived books. The filter has been dry-run against copies
of the real files (72 → 10, 63 → 1, 6 → 3, all rows still aligned) and none of it has been run
against `data/live`. Nothing under `data/live/`, `runs/` or `research/` was rebuilt, pruned or
deleted to produce this document.

```bash
cd ~/polycrawler2

# 1. Archive, never delete.
mkdir -p data/live/archive-2026-11-10
cp -p data/live/signals.csv data/live/signalsLane2.csv data/live/signalsLane3.csv \
      data/live/execStamps.csv data/live/laneCloses.csv data/live/laneMarks.csv \
      data/live/openPositions.csv data/live/trajectory.csv data/live/archive-2026-11-10/

# 2. Keep only rows written before the replay began (alertTs < 2026-10-18).
uv run python - <<'PY'
import csv
from pathlib import Path
CUTOFF = "2026-10-18"
for name in ("signals.csv", "signalsLane2.csv", "signalsLane3.csv"):
    path = Path("data/live") / name
    rows = list(csv.DictReader(path.open(newline="")))
    if not rows:
        continue
    fields = list(rows[0])
    keep = [r for r in rows if r["alertTs"][:10] < CUTOFF]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(keep)
    print(f"{name}: kept {len(keep)} of {len(rows)}")
PY

# 3. Drop the books that were computed from the bad rows so the chain rebuilds them.
rm data/live/execStamps.csv data/live/laneCloses.csv data/live/laneMarks.csv \
   data/live/openPositions.csv data/live/trajectory.csv

# 4. Restart the watcher so writtenTs starts being recorded, then rebuild the chain.
pkill -f "scripts/liveWatcher.py"
./scripts/dailyCatchup.sh
uv run python scripts/paperLaneMarks.py
uv run python scripts/laneWeekly.py
```

Step 2 preserves the old 13/13/15 column lists, so `writtenTs` is still withheld and `entryTs`
keeps falling back to `alertTs` for the kept rows. The alternative is for step 2 to write the new
header and pad the kept rows with an empty `writtenTs` — the difference between "the old rows are
honest about not knowing when they were written" and "the old rows claim a blank". That choice is
open, and it is one line either way.
