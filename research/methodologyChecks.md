# Methodology checks — the attack doc's top-3, executed

Runs 2026-10-17 (`logs/methodologyChecks.log`, plus `logs/methodologyChecks.log.append`
for the A8 tail). Specs come verbatim from `research/methodologyAttack.md` A3/A4/A8
and its audit-taught priority list. Conventions unchanged: dirs graded separately,
seeded machinery by import, no shipped-rule changes.

## Check #0 (added by handoff): the fade candidate under episode regrouping

R3's Q2 fade result (`research/oosFailureDiagnosis.md`: OOS ALL p5 +0.108,
P(>0) 0.999, 151 entries / 30 events) passed its pre-registered per-event gate —
and its own bottom line required this exact regrade before any candidacy.
Script: `scripts/research/fadeEpisodeRegrade.py` (rebuilds the fade population per
`oosFailureDiagnosis.q2Fade` verbatim, then `episodeGate`/`composeVerdict` from
`scripts/research/episodeTransport.py`; K* = 28, data-derived on the OOS tape).

| metric | value |
|---|---|
| episodes (events→episodes) | 30 → **9** |
| top episode | ep1 (iran enrichment/airspace cluster), **126/151 entries** |
| top-episode PnL share | **108.9%** of the population's total |
| epP / epP5 | 0.718 (< 0.80 bar) / −0.471 |
| ex-top ret | **−0.103** |
| per-event gate vs episode gate | PASS vs **FAIL** |
| composed verdict | **FAIL — ARTIFACT** |

The fade PASS was the same Iran episode-factory wearing the opposite sign:
1230 of 151 entries sit in one 57-slug account-overlap episode spanning
Oct-2024→Sep-2026; drop it and the fade is negative. One-line retirement note
appended to `research/oosFailureDiagnosis.md` Results. **Both sides of the fresh
≤0.35 burst die the same death** — copy (per-event) and fade (episode).

## A4 — freshness gates are unidentifiable on the tape (CONFIRMED)

`scripts/research/ageProbe.py` (+ cache under `data/raw/ageProbe/`), 50 sampled
shipped-cell accounts classified `atAccFirst` on `[data/oosExpansion]` — the
population whose "fresh ≤5d / ≤3 markets" gate is decided by the fill tape alone.

| verdict | n |
|---|---|
| verifiable via `/activity` | 22 |
| … secretly >5d old at entry | **19** (median true age 64d) |
| … secretly >3 markets | 16 |
| … failing at least one gate | **20/22** |
| truncated (≥1000 pre-entry trades → certainly old) | 5 |
| no pre-entry TRADE rows (unresolvable) | 23 |

Interpretation: among gradable accounts the fresh gate is right 2 times in 22.
~49% of shipped-cell entries sit in this unidentifiable class. Consequences:
(1) the entry population is "first-trade-on-our-tape", not "fresh wallet" — a
real whale could walk in mid-history and read as day-0; (2) any live rule that
mirrors this gate inherits nothing observable; the live watcher's `/activity`
rescue is the correct primitive — the RESEARCH side should adopt the same
one-time age-verification on flagged copies before it ever publishes a gate
again. Flaw **confirmed HIGH**.

## A3 — episode-gated regrade of prior verdicts

`entrySweep --episodes` (in-sample 480-cell grid, K*=34 in-sample-derived) and
`oosTransport --episodes` on both OOS pulls (K* derives per tape; 28 on HOLD).

| tape | result under composition |
|---|---|
| in-sample `[data, data/universe]` | $10k/≤0.35 family **marginal PASS** (epP 0.801 vs 0.80 bar, epP5 −1.0, exTopRet −0.034..+0.238 — zero headroom); shipped-adjacent cells flip; deep cells DEGENERATE |
| OOS-60 `[data/oos]` | 48/48 candidate cells **INCON** composed (tape too thin for the episode floor) |
| HOLD `[data/oosExpansion]` | 48/48 candidate cells **FAIL** composed |

Verdict composition can only add a FAIL (episodeTransport design), and on the
only tape with mass (196 fresh events) it fails everything — the transport
decision is unchanged, now measured under the honest event-counting. Note:
`data/entrySweep/oosTransportCells.parquet` now holds the HOLD episode-view run
(derived artifact — regenerable by rerunning oosTransport with/without
`--episodes`).

## A8 — fee handling (IN FLUX: crawl running)

Gamma dropped `condition_ids` batching entirely (verified live), so fees resolve
per-condition against the CLOB API (`taker_base_fee`/`maker_base_fee`) —
`scripts/research/feeMarkRegrade.py` crawled the graded cells' condition ids at
≤4 req/s (tail: `logs/methodologyChecks.log.append`, summary
`data/raw/feeMarkRegrade/summary.json`), and regraded all three flagship cells
net of 10% taker. **Result: 0.0% of entries and winners ride fee markets on every
graded lane — the drag is exactly 0.0pp everywhere** (in-sample shipped +1.169
→ +1.169, flagship +1.849 → +1.849; HOLD −0.541/−0.712 unchanged and still dead).
Consistent with geopolitics being fee-free per official docs. Verdict: A8
**killed for the graded military lanes** — fees never were a confounder here.
The residual risk is generative: any future NON-military universe must re-run
this fee attach (R6's third-universe census now carries a fee-share readout on
accentuation freshness, so the check is cheap there).

## Which prior verdicts change

1. **Fade candidate: RETIRED** (check #0/episode view) — R3's Q2 verdict flips
   PASS → FAIL/ARTIFACT; the one-line note is in its doc.
2. **In-sample shipped cell**: episode view already knew it
   (`research/episodeResample.md`: K=12–14 flip point); A3 re-measured it —
   the $5k/≤0.35 shipped rule fails composition; the $10k family survives only
   at the 0.80 bar with zero headroom and a −1.0 episode tail — nothing there
   to trade.
3. **Everything OOS-negative stays negative under episodes.** The transport
   conclusion of §9.2 stands, now with the episode gate attached.
4. **Any future gate using "fresh wallet"** must carry the A4 fix:
   one-time `/activity` age-verification (the liveWatcher primitive) on the
   research side, not the tape's first-trade proxy.

## pytest

Suite state at completion of checks #0/A4/A3: `uv run pytest` green per run
150 (verbal; A8 regrade touches only research scripts — no src changes).
