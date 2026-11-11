# SPEC vs code — the divergences, documented

`SPEC.md` is v0.2.0-draft, mtime 2026-10-08. The code moved on. This note records where
they disagree and which side should change, so nobody has to guess and neither document is
rewritten silently.

Three divergences are treated in full below because they are the ones that mislead a reader
into building the wrong thing. The same audit produced 32 more; the highest-severity of those
are tabled at the end, and the full set with file:line for every row is in
`~/reports/polycrawler2/phase0/03-spec-divergences.md` on the dev box (not in the repo).

## 1. The `prices` table is specified and not implemented

**SPEC says** (§4): a `prices` table, `ts, marketId, outcome, price`, sourced from the CLOB
`prices-history` endpoint. §3 says `pc2 fetch` downloads "markets, trades, prices, and funding
data". §6.5 defines the fill price as "the market price `delaySec` after their fill, plus
`slippageBps`" — which is exactly what a price history is for.

**Code does** no such thing. `fetch.py` defines two schemas (`marketSchema`, `fillSchema`) and
`runFetch` writes two parquet files (`fetch.py:78-79`). There is no call to
`clob.polymarket.com` and no import of `py_clob_client` anywhere in `src/`, and
`data/prices.parquet` does not exist in any of the five data roots.
`grep -rn "prices-history\|prices.parquet" src tests scripts` returns nothing.

Prices are instead reconstructed from the trade tape: `priceMove.buildPriceTape`
(`priceMove.py:178-233`) emits the last print per `(marketId, outcome, ts)` and synthesises the
complement `1 - p` for two-outcome markets (`:185,225`); `priceAt` (`priceMove.py:236-259`) is
an as-of join with a 6-hour `staleWindow` (`priceMove.py:18`). `backtest._prices`
(`backtest.py:255-278`) prices entries and exits from that tape.

**What that costs.** A market with no print inside 6 hours has no price at `t + delaySec`, and
`backtest.py:420` silently skips the trade (`if shares <= 0 or ourPrice is None: return`). So
execution is conditional on somebody else having traded recently — a selection correlated with
the attention the strategy is trying to measure, and recorded nowhere. The same null-quote path
turns an unexitable `followCluster` exit into a mark at a 3,650-day horizon
(`backtest.py:31,462-490`). Anyone reading `research/priceMove.md` is reading a study of markets
with continuous prints.

**Recommendation: two separate things, and only the first is uncontested.**

*Do now, on the code side* — delete the silent skip and record it. A dropped entry and a mark
where an exit was intended are both invisible today; a `noPrice` counter in `summary.json` plus
an explicit skip path costs nothing and makes the existing numbers honest. Then write the tape
and the 6-hour tolerance into §4/§6.5 as a **stated modelling decision** rather than leaving
§6.5 promising a CLOB price nobody fetches.

*Needs the owner's call, not a doc edit* — whether to build the `prices-history` fetch at all.
The case for it is that `clobTokenIds` is already fetched and persisted on every market row
(`fetch.py:39,156`), so the identifier is paid for; note no module in `src/` reads it, five
scripts do (`liveWatcher.py:142`, `paperLanes.py:211`, `bookExecStamps.py:104`, `execute.py:110`,
`research/duneOrderBurst.py:240`). The case against is real and was missed on the first pass:
for a market with no print in six hours, a CLOB midpoint fill is **more optimistic than no
fill**, so preferring a quote trades a transparent, nameable selection bias for an opaque
optimistic-fill bias — inside a backtest whose whole question is whether a delayed copy is
executable. It also cannot both change measured results and preserve them; the fallback only
preserves the numbers in exactly the cases the fetch fixes. So: not a "dropped capability to
restore", a modelling choice with a real trade-off.

## 2. `discovery.py` is a package, and half of it is a fork of itself

**SPEC says** (§9): `discovery.py # suspicious accounts → funders → origins → parents` — one
file. §9's closing paragraph says discovery "only talks to the rest through `data/` and
`parents.parquet`".

**Code does**: six substantive modules plus `__init__.py` — seven files, 4,037 lines.

| File | Lines | Owns | On the live path? |
|---|---|---|---|
| `engine.py` | 2,103 | everything: step-1 flagging, activity enrichment, Etherscan transfers + hub classification, hop discovery, union-find clustering (`buildFundingClusters`, 224 lines), the Relay origin layer, co-trade matching, all five output frames | yes |
| `mergeScores.py` | 331 | audit layer: `buildEdges` → merge planning, per-edge evidence, fail-closed thresholds | yes |
| `funding.py` | 752 | Etherscan scrape **plus a complete Alchemy `getAssetTransfers` path** | no — only `TransferRow` is imported, for typing |
| `flagging.py` | 344 | step-1 flagging, duplicated | no — only `splitCutoff` is imported |
| `activity.py` | 315 | Data API `/activity` + a recreational-market classifier `engine` does not have | no — nothing imports it |
| `links.py` | 181 | the seven pair generators, `anchorPairs`, `matchTimes` | no |
| `__init__.py` | 11 | `from … import *` re-export of `engine` (`:11`) | yes (facade) |

The duplication is verbatim, not conceptual: re-derived by AST dump plus text diff, 9 of 12
definitions in `flagging.py`, 16 of 37 in `funding.py` and 4 of 12 in `activity.py` are
byte-identical to their `engine.py` counterparts. The exception matters — `etherscanCall`
(0.32 similar), `classifyProbe` (0.54) and `fetchProbe` (0.71) have **forked**, so two
implementations of the hub rule exist and the engine's is the one that runs. Same for
`coTradePairs`. `tests/test_links.py` and `tests/test_clusters.py` import through
`polycrawler.discovery`, i.e. they test the engine copies, so the module copies are untested.

§9 is also wrong about the coupling. No module in `src/` reads `parents.parquet`;
`backtest.loadInputs` (`backtest.py:891-903`) reads `data/suspicious.parquet` +
`data/clusterAccounts.parquet` instead, and `suspicious.parquet` is not in the SPEC at all. Two
scripts *do* read `parents.parquet` (`scripts/linkComposition.py:93` treats it as a required
baseline, `scripts/research/oosClustersPostcheck.py:81`), so the write is not dead — do not
delete it on the strength of §9.

**Recommendation: change the SPEC, having first removed the genuine dead weight.** Delete
`flagging.py`, `links.py` and the unused Alchemy half of `funding.py` — all verbatim forks whose
engine copies are the ones that run and are tested — *then* write §9 against code that will not
move again. Keep `activity.py`: it is not a pure duplicate, it carries the only implementation
of the recreational-market classifier, so either port that classifier or file `activity.py` as
research code rather than dead. Record the `engine.py` split (2,103 lines, a 224-line
`buildFundingClusters`) as debt instead of implying §9's one-file promise is anywhere near true.

## 3. `web3.py` is in the SPEC's stack and nowhere in the repo

**SPEC says** (§9): the stack is "Python 3.12, `uv`, Pydantic, Polars, httpx, **web3.py**,
Typer, pytest".

**Code does** not use it and does not have it:

| Check | Result |
|---|---|
| `grep -rn "import web3\|from web3" src tests scripts` | 0 hits |
| `grep -rn web3` across the same | 0 hits, not even a comment |
| `pyproject.toml` dependencies | `httpx, polars, py-clob-client, py-clob-client-v2, pydantic, pyyaml, typer, websockets` |
| `grep -c web3 uv.lock` | 0 — not present at any depth |
| `py-clob-client` / `py-clob-client-v2` transitive deps | `eth-account, eth-utils, httpx[http2], poly-eip712-structs, py-order-utils` (+ `py-builder-signing-sdk`, `python-dotenv` in v1 only) — no `web3` |

On-chain reads are two hand-rolled httpx paths instead: Etherscan V2 proxy calls for transfer
history and `eth_getCode` (`engine.py:735-779,869-973`), and Alchemy JSON-RPC
`eth_blockNumber`/`eth_getLogs` with hand-decoded `Transfer` topics for payout confirmation
(`fetch.py:425-503`; `transferTopic` at `fetch.py:388`; the decode is `:437-448`). Order signing
is `py-clob-client-v2` (`scripts/execute.py:30`).

The stack list is wrong in both directions: `web3` is listed but absent, while
`py-clob-client`, `py-clob-client-v2`, `pyyaml` and `websockets` are present but unlisted.

**Recommendation: change the SPEC.** Drop `web3.py`, add the four missing dependencies, and add
one sentence naming the two RPC paths — the repo's whole on-chain surface is one event topic
plus `eth_getCode`, which genuinely does not need an ABI encoder, and the next person adding an
on-chain call would otherwise reach for a library that is not installed. Almost certainly
leftover from the v0.1 layer: `archive/v1/pyproject.toml:15` carries `web3>=7.0.0`.

## Also found

32 further divergences, of which these are the highest severity. All point at the SPEC except
where noted.

| ID | SPEC vs code |
|---|---|
| SD-12…16 | §6 describes a net-exposure follower. The code copies 10-minute BUY bursts: net is per `(group, market, outcome)` signed shares and Yes−No is never formed; sizing mirrors their shares, not their net (`strategy.py:264`); entry fires on a burst and `followAdds` defaults True; exit is an armed latch. |
| SD-22 | §5's signal table has five signals with "Won — required". The code scores four and applies `isLate` as a hard gate (`engine.py:335-368`), so the SPEC's Step 1 selects a different account set. |
| SD-17…19 | `fetch.from` is `fromDate` in code and `extra="forbid"` means a SPEC-shaped YAML raises. `maxFlagLeadHours: 168` is a hard gate the SPEC omits (`engine.py:366-367`). 11 strategy keys are undocumented (`config.py:62-77`), including `sizing`, `copyRule`, `accountSelection`, `followAdds`. |
| SD-25, 26, 30 | §2 rule 1 ("no live code until backtests show an edge") is false: `scripts/execute.py --live` places orders (`:153,171-176`) and `liveWatcher.py` runs from cron. Rule 2's purity holds for `strategy`, `backtest`, `priceMove`, `sweep` and `config` but fails for `discovery/engine.py` (21 httpx call sites). Five of §11's **ten** "not in v0.2" items ship. |
| SD-11 | §5 calls "how many clusters kept winning after splitDate" the first number to look at. Nothing computes it — no command, function or summary field. |
| SD-20, 24 | `minCoTradeMarkets` is declared, sits in two YAMLs (`configs/base.yaml:31`, `configs/oosExpansionDiscover.yaml:27`), and is read by nothing; `coTradePairs` sums matches across markets, which looks like what that dead knob was meant to fix — intent is not recoverable from the code. |
| SD-07…10 | `runs/<hash>/` hashes strategy params only, so two runs differing in `splitDate` overwrite each other; `params.yaml` cannot rebuild a run; no `parents.parquet` snapshot; `summary.json` has no cluster count. |
| SD-05 | §3 says `pc2 sweep` runs discover + backtest combos. `loadSweep` rejects any key outside `BacktestParams` (`sweep.py:52-54`), so discovery cannot vary in a grid at all. |
| SD-23 | Nothing in the SPEC mentions the prefilter: above 3,000 candidates discovery silently adds `avgBuyPrice <= 0.7` to selection (`engine.py:42-43,440-444`), so results depend on how much data was fetched. |
| SD-27 | §2 rule 3 says every knob is in config. `burstWindow` (10 min, `strategy.py:18`), `staleWindow` (6 h) and `markHorizon` (3,650 d) are hardcoded and all three change results. |
| SD-28, 32, 34 | `priceMove.py` (836 lines) is absent from §9. `scripts/` + `scripts/research/` + `research/` + `configs/` are undocumented, and about 125 of 196 tests exercise that surface. Five data roots exist and several published numbers depend on which combination is used. |
| SD-35 | §4's column lists are incomplete: `markets` adds `eventSlug, resolvedAt, clobTokenIds, outcomes`, `fills` adds `txHash`. `resolvedAt` gates step 1 and `txHash` is the dedupe key, so these are load-bearing, not detail. |
| SD-21, 31, 33 | Default config differs per command (`splitDate` 2026-01-01 in `base.yaml` vs 2026-03-01 in `insiderCases.yaml`, `cli.py:28,46,177,212`). §12 Q1 says Alchemy is unusable while `confirmSolverPayout` uses `ALCHEMY_API_KEY` (`engine.py:1929-1956`) and degrades to `None` without it. §3's diagram ends "→ `sweep` / `compare`" and there is no `compare`. |

Full evidence, file:line for every row, and a reconciliation order:
`~/reports/polycrawler2/phase0/03-spec-divergences.md`.
