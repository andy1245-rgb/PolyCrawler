# Sports favorites at T-7d — falsification/verification study (PRE-REGISTRATION)

**Status: registered 2026-10-17, BEFORE any data fetch for this study.**
This document registers the replication rule, our grading gates, and the kill
rule before the crawl in `data/raw/sportsT7d/` and any grade takes place.
Study family: `research/ideaGenAlpha.md` §2(h).

## 1. Source claim, verbatim

Repo (re-fetched 2026-10-17, HEAD): https://github.com/sturzael/polymarket-edge-research
Key files re-read: `experiments/SYNTHESIS_flb_cross_venue.md`,
`experiments/e23_stratification/SYNTHESIS.md`, `experiments/e16_calibration_study/FINDINGS.md`,
`experiments/e16_calibration_study/05_fixed_time_calibration.py`.

### 1.1 The exact extraction rule (from their code, `05_fixed_time_calibration.py`)

- Universe: resolved Polymarket sports markets, sampled per-category
  (`--per-category 150`), volume `≥ $5,000`, market duration
  (end_date − created_at) `≥ offset_days + 1` = 8 days.
- Anchor: `target_ts = end_date − offset_days` (`end_date` = game date),
  offset 7 days ("T-7d").
- Window: **±12 hours around T-7d** (`--window-hours 12`).
- **Tape convention is NOT a trailing print in their rule**: they compute a
  **size-weighted VWAP of YES-equivalent price over the whole ±12h window**
  (both outcome tokens' prints, mapped to YES space: `outcomeIndex==1 → 1−p`),
  requiring **≥ 3 prints** in the window; markets with <3 prints are excluded
  ("weren't actively priced at T-7d").
- Bucketing: fixed 5pp buckets `[(i/100, (i+5)/100) for i in range(0,100,5)]`,
  `bucket_mid = lo + 0.025` (e.g. 0.55–0.60 → 0.575).
- Statistic: per-bucket `yes_rate` vs `deviation = yes_rate − bucket_mid`;
  headline e16: 0.55–0.60 → yes_rate 0.875 (n=32, z=5.1); e23 refresh:
  yes_rate 0.833, deviation +25.8pp, z=7.6 (n=120).

### 1.2 The e23 stratification filter (their deployment scope, verbatim from §7)

Entry criteria (ALL must hold):
- Sport ∈ {MLB, NBA, NFL, NHL}
- Sub-category = game_outcome (head-to-head dated team/player match)
- Market duration ≤14 days (listed within 2 weeks of event)
- **Total volume in ±12h around T-7d ≥ $5,000**
- YES price at T-7d ∈ [0.55, 0.60)
- max_single_trade_usd in window ≥ $2,000 (depth sanity check)

Their execution-adjusted claim (Agent F): +23.8pp net at $500 entries at
3bps; "fees are a rounding error (<0.4pp even at 15bps V2)". Cross-venue
control: Betfair ≤±6pp, Azuro ≤+3pp at their own (close-anchored) windows —
the +25–30pp cell is venue×T-7d-specific and not replicable off-Polymarket.

### 1.3 What we grade differently (and why)

- **Grade on our own tape, not theirs.** Their z=7.6 is a calibration
  statement; we must convert it to tradeable return with our gates.
- **Tape conventions:** per event, the single moneyline market (see §2
  identity rules); snapshot at T-7d, favorite = token whose pre-T-7d read
  is higher (counter-token print => 1-p when the favorite side is
  untraded). Two registered conventions:
    - **their ±12h size-weighted VWAP** (favorite space, ≥3 prints) — the
      source-faithful rule — and
    - **trailing last print in [T-7d−12h, T-7d]** — intended primary.
- **PROTOCOL DEVIATION, disclosed BEFORE grading (no band was ever graded
  on the trailing read):** first-pass inspection of the pulled tapes shows
  a boundary sweep artifact: prints at ≥0.95 cluster at the END of the
  trailing window (10–16% of the last two deciles vs ≤2% mid-window;
  217/244 events end the window with a ≥0.95 print at significant size,
  e.g. a 4,000-share print at 0.999 seven days before a game priced ~0.63
  on the body of the tape). A "favorite" selected by the last pre-T-7d
  print is therefore sweep-selected, not book-priced. The PRIMARY
  convention is accordingly swapped to the source-faithful ±12h VWAP
  (their e16 rule, verbatim); the trailing print remains registered as a
  robustness/STRONG-PASS confirmation column only. Entry economics per
  convention use that convention's own price for both the $100 copy and
  the band bucketing (50bps exec; hold to resolution).
- **ANCHOR CORRECTION, second protocol deviation disclosed BEFORE any
  band was accepted as graded:** the first end-anchored grading pass
  produced winRate 1.000 in the 0.55–0.60 bucket — mechanically impossible
  for a pre-game anchor, which exposed the problem: Gamma `endDate` is NOT
  the game close for the modern sports books (NFL: game-day morning; MLB
  V2-era: ~8 days AFTER the calendar game — measured on the crawled
  payloads). Anchor is therefore the game calendar date embedded in the
  event slug (`<sport>-<team>-<team>-YYYY-MM-DD`) at 12:00Z; legacy
  dateless slugs keep their `endDate − 7d` anchor (their endDate =
  game-day noon, verified on 2024-05..2024-10 examples). The ± day window
  tolerance registered above covers the clock-time uncertainty.
- **Volume floor: ≥ $50k market volume** (task brief; ~8.5× their $5k floor —
  stricter, so this is a conservative replication on a more liquid sub-slice).
- Horizon: exactly T-7d (7.0d ± 0 before date arithmetic; the trailing window
  provides the tolerance). T-14d/T-5d/T-3d only run for timing sensitivity if
  the headline PASSes (§5).

## 2. Registered replication plan

- **Scope/crawl (corrected pre-grade, before any fills-based grading):**
  Gamma `/events/keyset`, `closed=true`, `tag_slug` ∈ {mlb, nba, nfl, nhl} (the
  repo's scope), `volume_min=50000` (event level, server-side). Identity of
  the game-outcome moneyline (verified on the cached event payloads before
  any grading):
  - modern era (≥ 2024-08): market `slug == event slug`, question contains
    `vs.` (e.g. `nfl-ind-was-2026-10-04` = "Colts vs. Commanders");
  - 2024 legacy singles: `who-will-win-game-N-of-*` / trailing `-game-N`;
  - binary non-Yes/No outcomes; series/futures/advance/finals/matchup
    markets and spread/total/nrfi/inning/1h suffix markets excluded
    (the e23 game_outcome filter); one market per event (the moneyline;
    alternates lose by the suffix rules above), so event = unit.
- Volume/duration filters per market: `volumeNum ≥ $50k`, listing lead
  (market `createdAt` → event `createdAt` → market `startDate`) to the
  **game date (slug-embedded, anchor correction above)** ≥ 8d — the third
  correction, disclosed pre-grade: the ≤ 8d lead check measured against
  `endDate` admits V2-era MLB markets listed only ~5 days before the game
  (their padded endDate covers the slack). `market.startDate` is the game
  start-time slot for sports markets — NOT the listing date.
- **Sample (third disclosed pre-grade change):** all qualifying events if
  n ≤ 3200; else deterministic seeded sample (seed 42) stratified to
  800/sport, sorted by event id. The brief's 150–300-events target assumed
  T-7d tape coverage of ~50-100%; measured pre-T-7d coverage on the first
  300-event sample was 5.7% (17/300, all NFL) — the registered n ≥ 20 band
  gate is unattainable at that size, so the crawl is extended with the same
  stratification/seed discipline.
- **Fills:** data-api BUY fills (takerOnly=false, the shipped pipeline)
  via `polycrawler.fetch.collectTrades` — the thirdUniverseScan walker
  (R6 after_cursor keyset crawl for events; collectTrades backward-walk for
  the 10k-offset wall). One cache file per market under
  `data/raw/sportsT7d/<tag>/trades_<id>.json`; events pages under
  `events_<tag>_<n>.json`. Rate cap 4 req/s on both hosts (HttpSession).
- **Grade:** per price band in
  {[0.50,0.55), [0.55,0.60), [0.60,0.65), [0.65,0.70), [0.70,0.75),
  [0.75,0.80), [0.80,0.85), [0.85,0.90), [0.90,0.95)} on the trailing-print
  favorite price: n, realized winRate, implied (band mid), calibration excess
  (= winRate − mid) vs **break-even winRate** at that price with 50bps exec
  cost, mean ret per $100 copy, per-event bootstrap p5 / P(>0) (BOOTS=1000,
  seed 42, event-level pnl/cap — the entrySweep evaluate machinery with a
  single-row-per-event frame), top-event share (max single-event pnl / total
  pnl, oosTransport convention), time-half split at 2025-06-01 (entrySweep
  HALF_SPLIT), fee-net regrade via feeMarkRegrade-style winner-pays-10% on
  fee-flagged markets (fee flags crawled per condition_id from CLOB
  `GET /markets/<id>`; sports are NOT assumed fee-free).
- **MIN_CELL = 20** events per band; bands below that are reported as
  INCON (not graded).
- **Secondary cell (e23 stratified replica, pilot):** headline band ∩
  (±12h window volume ≥ $5k) ∩ (lifespan ≤14d). Gate applied only as
  pilot evidence, clearly separated from the primary family decision.

## 3. Registered gates (mechanical PASS/FAIL)

Per band: **PASS iff n ≥ 20 AND p5 > 0 AND P(>0) ≥ 85% AND top-event share
< 60%.** Time-half split is reported as diagnostic evidence only (both-half
positivity is desired but not gate-blocking, per the abridged idiom in
ideaGenAlpha §1).

Primary family decision ladder (registered, mechanical):
1. **HEADLINE test** = band [0.55,0.60), trailing-print convention:
   calibration excess (winRate − implied) ≥ +8pp AND band gate PASS.
   `<8pp` excess = citation-confirmed decay → NO-GO.
2. **EDGE EXISTS** if headline passes AND at least one additional band
   passes its gate with excess ≥ +8pp.
3. **STRONG PASS (graduate to scanner design doc)** if headline passes with
   excess ≥ +15pp (≥ half the cited 25.8pp per ideaGenAlpha §2(h) kill
   criterion) under BOTH tape conventions (trailing print AND their ±12h
   VWAP).
4. **Kill rule (explicit):** if realized winRate ≈ implied everywhere
   (every graded band's excess ≤ +3pp and no band PASSes its gate), the edge
   does NOT exist on our tape → **NO-GO: no live-lane capital on sports
   favorites.** This is the verbatim dead-check requested before any fetch:
   "if our calibration shows favorites correctly priced vs realized, the
   edge does NOT exist on our tape."

Fee handling: primary gate numbers are exec-50bps (fee-free assumption);
a per-band fee-net regrade line rides beside them. If fee-crawl says a
material share (>5%) of the sample sits on fee markets, the NO-GO/PASS
decision reruns on the fee-net numbers automatically.

## 4. Deliverables

- `scripts/research/sportsT7d.py` (single entry point: crawl → snapshot →
  grade → report; caches append-only under `data/raw/sportsT7d/`)
- `logs/sportsT7d.log` (one grading run)
- Tables + mechanical verdict rendered by the script; human readout
  appended to this file in §6 after the run.
- pytest green, ruff clean, RSS < 4GB, no git commits, `data/live` and
  crontab untouched.

## 5. Verdict-in-advance

Registered expectation: the 0.55–0.60 bucket n on our $50k-floor tape will
be small-ish (their e23 headline was n=120 on a looser $5k floor across ~3
years); an underpowered-but-clean answer is an acceptable outcome and gets
recorded as such (INCON with directional excess) rather than tortured.
Family GO requires the mechanical ladder above, full stop.

## 6. Post-run readout (2026-10-17, run: logs/sportsT7d.log)

**Verdict: NO-GO-KILL (mechanical, registered ladder). No live-lane capital
on sports favorites at T-7d.**

### 6.1 What got graded

- Corrected-scope qualifying books (game moneylines, lead ≥ 8d to the GAME
  date, vol ≥ $50k): **mlb 2, nba 2, nfl 222, nhl 1217** (of 10,283 events
  crawled at vol ≥ $50k). Tape: 1,026 events (all qualifying for
  mlb/nba/nfl + 800/1217 NHL sample), fills pulled via the shipped walker
  (every market cached). Pre-grade protocol corrections are all disclosed
  above (§1.3/§2): moneyline identity, game-date anchor, sample expansion,
  and the trailing→VWAP primary swap (boundary sweeps break "last print").
- **T-7d tape coverage: 109/1026 events (10.6%) had ANY pre-T-7d print in
  ±12h**; 94 with the ≥3-print VWAP. Sport mix: **nfl 89, nhl 16, nba 2,
  mlb 2**. Rows sit at 2024-09 → 2026-10.

### 6.2 Headline numbers (T-7d, their ±12h VWAP, ≥3 prints)

| band | n | winRate | implied | excess | z | beWR | ret/$100 | p5 | P>0 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.50-0.55 | 16 | — | — | — | — | — | — | — | — | INCON |
| **0.55-0.60** | **21** | **0.476** | 0.575 | **−9.9pp** | −0.92 | 0.578 | **−$17.77** | −$50.7 | 0.13 | **FAIL** |
| 0.60-0.65 | 17 | — | — | — | — | — | — | — | — | INCON |
| 0.65-0.95 | 34 | — | — | — | — | — | — | — | — | INCON (all < MIN_CELL) |

- Fee-net regrade (28.6% of headline-cell winners on fee-marked
  conditions): ret −$17.77 → −$19.45 — fees only worsen it.
- **Direct rejection of the source magnitude:** they report 0.833–0.875
  yes_rate in this bucket; we observe 0.476 (n=21) → **z = −4.4 against the
  claimed 0.833**. Even the sweep-flattered trailing-print column reaches
  only 0.680 (n=25, excess +10.5pp, z_mid +1.06, z vs claim −2.05, gate
  FAIL: p5 −$9.73, P>0 0.84). There is no convention under which our tape
  shows the published +25–30pp.
- Kill rule triggered: headline gate FALSE, excess −9.9pp (< +8pp decay
  threshold); the only graded cell prices favorites BELOW break-even →
  **NO-GO-KILL** per the registered ladder (favorites are not "correctly
  priced" in the weak sense either — they are noise-to-overpriced at n=21,
  but the registered kill criterion is excess ≈ priced, and the sub-break-
  even point estimate settles it the same way).
- e23 stratified pilot cell (≤14d lifespan ∩ ±12h window vol ≥ $5k ∩
  headline band): **n = 1** — structurally empty on the current tape.
- Timing sensitivity not expanded (ladder kills before T-14d/T-5d/T-3d).

### 6.3 Structural findings (as important as the verdict)

1. **The deployment universe mostly no longer exists.** With the corrected
   game-date anchor: MLB/NBA book TWO qualifying ≥8d-lead markets combined
   (V2-era books list ~5d and <8d pre-game; the cited MLB-primary mechanism
   is unreplicable at T-7d on today's structure). NFL lists ~40d ahead but
   only ~40% of books trade at all by T-7d. NHL lists early (1,217 books ≥
   8d) but only 2% print at T-7d (orphaned listings, dormant mid-life).
2. **The published edge's own scope (n=120 bucket cells) already assumed a
   richer tape than today's**; the joint stratification that produced their
   forward plan (≤14d ∩ ≥$5k window ∩ depth ≥ $2k) yields ~1 cell/1,026
   graded events here.
3. Even if the calibration gap existed, the visible universe is ~20–40
   in-band books/season (NFL-dominant) — an order of magnitude below "the
   most frequented retail edge" framing in ideaGenAlpha §2(h).

### 6.4 Bottom line

**Do NOT spend live-lane capital on sports favorites at T-7d.** Falsified
on our tape (registered kill rule), rejected against the claimed magnitude
at z = −4.4 in the one well-populated cell, and the tradeable universe is
structurally ~empty outside NFL anyway. Record as citation-confirmed decay
plus structural non-existence; the ideaGenAlpha §2(h) family decision is
NO-GO, with the T-7d favorite scanner idea closed. If it ever comes back,
the cheap re-check is: crawl-only + trailing/VWAP snapshot on new listings
(no fills pull needed to see whether T-7d books even exist).

### 6.5 Deliverables & hygiene

- `scripts/research/sportsT7d.py` (single entry point; caches under
  `data/raw/sportsT7d/`, ~2.9GB fills cache; grade record:
  `data/raw/sportsT7d/grade.json`); `logs/sportsT7d.log` (complete run).
- pytest: 175 passed; ruff: clean; peak RSS ~450MB (< 4GB); no commits;
  `data/live`/crontab untouched; Gamma rides the 4 req/s HttpSession rail.
