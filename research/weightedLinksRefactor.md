# weightedLinks refactor — mergeScores two-pass review follow-through

The linkage machinery's buildFundingClusters union-find was wrapped by an
evidence/decision layer instead of retuned (recall-lift is unmeasurable at 6
clusters / 9 labeled courts; nothing here should be able to change which
accounts land in which cluster at shipped defaults).

## What changed per the two-pass design review

* **Merge path via decisions only.** The inline union-find merge loop moved
  to `src/polycrawler/discovery/mergeScores.py`. Every raw link edge becomes
  an `EdgeEvidence` (kind, both endpoints, evidence count + what it counts)
  and `planMerges` turns each into a `MergeDecision` (merge flag + printable
  rule). `buildFundingClusters` unions ONLY via merge decisions; edge
  presence still drives the `linkType` labels exactly as the old `union()`
  side effect did. `byFunder` and the hop `reached` map (parent scoring
  inputs) come back from the plan.
* **Two-sided gate rationale.** The seven link kinds are NOT one behavior:
  six strong money-flow kinds (direct, sharedFunder, sharedCashOut, hop,
  sharedOrigin, originSibling) merge at >= 1 edge — one corroborated
  collateral relationship. coTrade merges strictly at >= minCoTrades (2)
  matched BUY windows, because co-trading is not money flow; that gate now
  lives in the rule text at merge time, not only upstream in
  `coTradePairs`. The shipping truth: `defaultThresholds(minCoTrades)`
  reproduces today's unconditional merges bit-for-bit; the threshold dict
  plumbing is audit-only (a hypothetical `{"sharedFunder": 4}` flips merges
  and leaves the audited-but-unmerged edge label on both endpoints), and no
  shipped caller passes anything but the defaults. No tau sweep shipped.
* **Embeddings dropped.** The review's candidate "embedding similarity"
  signal was left out of edge construction entirely: on 42 member rows
  across 6 clusters there is no measurable lift, and an unmeasurable vector
  edge would silently glue strangers together. Reopen only if a labeled
  sample grows an order of magnitude.
* **coTrade evidence now counted.** `coTradePairs(..., withCounts=True)`
  returns (left, right, matched-window) triples; the count is the coTrade
  edge's `evidence`, and `minCoTrades` is restated in the per-edge rule
  ("coTrade matched BUY windows 3 >= threshold 2").

## Relay retire-yet maintenance note

`linkOrigins` still depends on the public Relay lookup
`GET api.relay.link/requests/v2` (`relayApi` in
`src/polycrawler/discovery/engine.py`). That route retires **2026-11-24**
(per-engine comment: its `limit` steps down from 2026-09-01; v3 only
returns the caller's own integrator requests). Any origin-chain upgrade —
e.g. richer sharedOrigin/originSibling groups — must swap the lookup out
before that date or the upgrade lands dead. Check the deadline before the
next origin-chain work item.

## Parity test results

`tests/test_mergeScores.py` locks the merge semantics against a verbatim
copy of the pre-refactor union-find, on one synthetic graph exercising a
direct edge (2 rows), a multi-window coTrade (3 windows, minCoTrades 2), a
sharedFunder hub (blocked) with two real funders, a shared cash-out, an EOA
hop through one grandparent with 2 legs, and sharedOrigin + originSibling
from one origin group:

* identity partition + per-account linkTypes vs the legacy merge (same
  component order at any hash seed),
* every decision auditing the rule that fired (evidence counts, thresholds),
* `defaultThresholds` fixtures reproduce the unconditional merge; a
  hypothetical threshold BELOW a kind's evidence flips the merge and the
  audited-but-unmerged edge keeps its label; a below-threshold coTrade
  window (1 room < 2) stays unmerged at defaults.

Result: **3 passed**, stable across `PYTHONHASHSEED` sweep (0…65535. Full
suite: **111 passed** in `uv run pytest`, green across the same sweep).

Notes fixed while finishing: component row order inside
`buildFundingClusters` follows set iteration, so membership assertions are
set-based (members of any component clearing `minSuspiciousAccounts` are
ALL included; components below the gate are documentedly absent).

## Composition audit

`scripts/linkComposition.py` re-runs the engine's funding pass into a
TEMP-COPY of the data dir (never the real `data/`; caches for etherscan/
relay ride along so a no-op replay is fully cache-served and offline), then
reports per config: old→new clusterId mapping, spread of each old cluster,
false-split detection (any old cluster over >= 2 new ids), false-fusion
detection (two old clusters sharing a new id), parent-label delta,
member-count delta by evidence type, clusterAlreadyCopied count
(funded/originSibling copy rows), and the pre-registered verdict rule
"trade delta <= +/-2 ⇒ no demonstrable effect, keep default".

Usage line:

    uv run python scripts/linkComposition.py --config configs/insiderCases.yaml --data-dir data

(ETHERSCAN_API_KEY from `.env`; `--config` must be the config the baseline
snapshot was produced with — its splitDate gates both funding uses and
coTrade windows. Not `configs/base.yaml`: splitDate 2026-01-01 sees no
Feb-2026 trades and the coTrade evidence drops to 0.)

Result on the `data/` snapshot (6 clusters / 42 member rows, read-only):

* mapping: all 6 old clusters → their own new id, spread 1 each
* falseSplits: {} — falseFusions: [] — parentLabelDelta: []
* member deltas by evidence type: coTrade 37→37, sharedFunder 4→4,
  funded 1→1, everything else 0→0
* clusterAlreadyCopied: 1→1
* **verdict: trade delta 0 ⇒ no demonstrable effect, keep default**
