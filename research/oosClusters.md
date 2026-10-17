# OOS expansion — wallet-cluster discovery on data/oosExpansion

Run: `uv run pc2 discover --config configs/oosExpansionDiscover.yaml` (HEAD `6d574d3`, tree clean at start).
Config: `configs/oosExpansionDiscover.yaml` — splitDate 2026-01-01, `fetch.dataDir: data/oosExpansion`, discovery section
mirroring `configs/eventUniverse.yaml` (`maxMarketsTraded: 15`, `maxFlagLeadHours: 168`, `minCoTradeMarkets: 2`,
Relay 1 req/s, `relayPageLimit: 50`). No label file: no ground truth exists on this fresh universe.

Tape: 200 fresh resolved military event slugs (iran 45 | ukraine-russia 45 | gaza-hamas 25 | houthis 15 |
hezbollah 15 | venezuela 20 | pakistan-india 10 | syria 10 | taiwan 5 | nato 8 | other 2), 10,666,464 fills,
962 markets — 376 resolved pre-split, 537 post-split, 49 unresolved. 2.84M fills before the split, 7.83M after.

## Step 1 — timing and flag pool

Step 1 alone: **19:00 wall clock, peak RSS 2.6 GB** (log `logs/discoverOosExpansionStep1.log`).
The 10.66M-fill profiling is minutes; the rest is per-candidate activity fetches (2,466 accounts, cached under
`data/oosExpansion/raw/activity/`).

- 6,524 winning-bet candidates → prefilter `avgBuyPrice<=0.7` (soft cap 3000) → **2,466 candidates**
- **14 suspicious accounts** (0.57% of candidates; the in-sample universe run gave 151/2455 ≈ 6%)
- All 14 pass exactly 4/4 signals: new (age ≤14d, most age 0.0d by tape), focused, longshot, big ≥$1k; every one
  also inside the 168h lead gate
- Best-bet profits $2.7k–$80k per account; concentrated on strike-timing events — 6 on
  `us-military-action-against-iran-by-saturday`, 5 on `israel-military-action-against-iran-before-july`, plus
  1 `us-military-action-against-iran-before-july`, 1 `us-strike-on-syria-by`, 1 `venezuela-election-winner`

The pool is **not degenerate** (≥10, clean insider profiles, right category), so the full pipeline proceeded.

## Full run — timing and network trace

Full discover: **4:29 wall clock, peak RSS 2.7 GB**, in-session (projection said ≪6h because 14 traced accounts
is ~6x smaller than the 89-account universe run that took 2h25m almost entirely on Relay pacing — measured, not
guessed). Log `logs/discoverOosExpansion.log`.

- accounts traced 14 · hubs 7 (incl. Relay solver `0xf70da…` and 6 other ≥50-counterparty hubs) · 8 funder probes
- collateral mix USDC.e 339 / pUSD 429 / USDC 12 rows; 780 funding rows, 4,048 Polymarket-contract transfers skipped
- Etherscan fetched 29 (fresh cache) · Relay: 3 bridge deposits → **3 origins resolved, 3 distinct origin users**
  (chains: Ethereum 2, Polygon 1), 17 relay calls, 9 rate-limit backoffs, 240.6s; solver payout re-verified on-chain
  via Alchemy (`payoutConfirmed True`, block 95675427)
- 93 origin-recipient rows across the 3 origin users (post-split Erkling: origin `0xe1ec6e…` kept bridging itself
  into 2026-09 from chain 728126428)

## Clusters — none

- **clusters 0** · `parents.parquet` 0 rows · `clusterAccounts.parquet` 0 rows
- co-trade edges **0**: on this tape the solo-fresh-big-bet profile dominates and nobody buys the same
  (marketId, outcome) within 10s twice across ≥2 markets — the 28-account co-trade behemoth from the universe came
  out of date-ladder markets, which these 200 events mostly lack
- no shared non-hub funder: each suspicious account's pre-split funding comes through hubs (Relay solver etc.)
- no shared origin wallet: the 3 Resolved origins map 1-to-1 to 3 different suspicious accounts

Largest cluster n/a. Link-type composition: empty (no cluster links at all).

## Recall / consistency check vs the battery fresh-big-bet rule

Battery rule (research/militaryCategory.md): single-market burst ≥$5k, avg price ≤0.35, account fresh ≤5d,
≤3 markets so far, military. Applied to the pre-split tape (burst approximated as the account's/(market,outcome's)
total pre-split buy sum — a deliberate superset of the strict single-burst cell):

- **191 accounts flagged** fresh-big-bet pre-split (bursts $5k–$186k at ≤0.35, tape age ≤5d)
- overlap with step-1 suspicious: **3 of 14** — the two rules index the same population but at different
  thresholds/burst windows; step-1 allows ≥$1k and ≤0.30 (avg) or the $5k/0.35 cell above
- **flagged fresh-big-bet accounts landing in clusters: 0** — trivially, because 0 clusters exist. The universe's
  ladder-market co-trade formation has no analogue on this fresh tape.

## Post-split survival — the money answer

**None. No cluster was found pre-split, so no cluster keeps winning after 2026-01-01. n = 0, plainly.**
One cluster surviving ⇒ note it; none ⇒ this is it.

Supplemental (account level, remaining-plus-realized PnL at resolution from tape resolution + post-split fills,
script `scripts/research/oosClustersPostcheck.py`, log `logs/oosClustersPostcheck.log`): the 14 suspicious
accounts' post-split positions net **≈ +$2,050**. Composition: the big Feb-2026 Lebanon-suspension and Iran
ceasefire traders (e.g. `0xfe6eee00…`, `0xcfe6f0d5…`) close their pre-split intel positions *after* the split for
+$1.0–1.3k each in realized profit, then mostly stop or place small new bets that lose (−$0.3–2.1k rows).
Consistent with `research/freshAccountSignal.md`: an insider's edge belongs to one event; flagged accounts do not
keep being profitable on later markets.

Verdict in one line: **on this 2.7x-larger fresh military tape, discovery finds 14 clean-looking lone insiders but
no cluster — the cluster-based copy strategy has nothing to copy OOS; the fresh-big-bet account rule remains the
only carrier of signal here**, and its OOS engine-validation is what `configs/oosExpansionEntryGrid.yaml` /
`oosExpansionEntrySweep.log` territory is for (separate question from clustering).

## Artifacts

| File | Rows |
|---|---:|
| `data/oosExpansion/suspicious.parquet` | 2,466 scored / 14 suspicious |
| `data/oosExpansion/funding.parquet` | 780 |
| `data/oosExpansion/origins.parquet` | 3 |
| `data/oosExpansion/originRecipients.parquet` | 93 |
| `data/oosExpansion/parents.parquet` | **0** |
| `data/oosExpansion/clusterAccounts.parquet` | **0** |

Logs: `logs/discoverOosExpansionStep1.log` (step-1 timing), `logs/discoverOosExpansion.log` (full run),
`logs/oosClustersPostcheck.log` (battery-rule recall + post-split PnL). Config: `configs/oosExpansionDiscover.yaml`.
Analysis script: `scripts/research/oosClustersPostcheck.py`. No git commits; data/live/ and scripts/liveWatcher.py
untouched.
