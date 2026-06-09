# PolyCrawler — Product & Technical Spec (v0.1.0)

> Living document. Source of truth for behavior, protocols, and analytics requirements.
> Repository: **PolyCrawler**

---

## 1. Purpose

Build a system that:

1. **Finds** Polymarket accounts likely connected to the same real-world operator (“parent” funding wallet + sibling accounts).
2. **Watches** new accounts funded by already-flagged parents **before they win** (ideally on first deposit).
3. **Mirrors trades** in **paper mode first** (no money required), then optionally live.
4. **Records rich analytics** so entry/exit rules, scoring weights, and thresholds can be tuned from real data.

**Core product sentence:** When money from a parent we already care about lands in a new Polymarket account, watch it; when they open a position, mirror (paper or live); when they exit, we exit; log everything for accuracy testing before risking capital.

**Non-goals for v0.1:** Perfect insider conviction, legal classification, beating Chainalysis/PolyInsider on generic fresh-wallet alerts.

---

## 2. Glossary

| Term | Meaning |
|------|---------|
| **Parent wallet** | On-chain address that funds Polymarket accounts (EOA, CEX withdrawal path, etc.). Primary identity anchor for clustering. |
| **Polymarket account** | Tradable address on Polymarket (deposit wallet, Safe, or proxy). |
| **Sibling** | Another Polymarket account funded by the same parent. |
| **Cluster** | Parent + all linked Polymarket accounts + derived scores. |
| **Cluster score** | Weighted quality of a cluster. Used **only** for discovery, flagging, and alert **ranking** — **not** for trade entry. |
| **Flagged parent** | Parent that met discovery criteria and is on the watchlist. |
| **Paper trade** | Simulated fill; no wallet or capital required. |
| **Session** | A bounded run of paper/live activity with its own stats. |
| **Global analytics** | Aggregated stats across selected sessions (configurable inclusion). |
| **Sell** | Closing/reducing a position on the order book before resolution. |
| **Redeem** | Cashing out winning shares after a market **resolved** (not a normal sell). |
| **Merge / split** | On-chain ops converting USDC ↔ outcome token pairs. v0.1: log only, no auto-trade. |
| **Position reconciliation** | If their share balance drops to zero but we missed the sell event, close our mirrored position anyway. |

---

## 3. Account types (detection timing)

Polymarket users arrive through different paths. Same protocols apply; **how early** we see them varies.

| Path | Typical first on-chain signal |
|------|------------------------------|
| **Deposit wallet** (new API) | Wallet creation (`WalletDeployed`) and/or first fund — **best** for zero-trade watch |
| **Gnosis Safe** | Safe deployment on-chain |
| **Website / proxy** (legacy) | Often first **fund** or first **trade** only |

Iran insider cases often use website-style accounts. Zero-trade detection is still valuable on fund; sometimes first clear signal is first trade.

**Factory addresses (Polygon mainnet)** — for implementation reference:

- Deposit wallet factory: `0x00000000000Fb5C9ADea0298D729A0CB3823Cc07`
- Proxy factory: `0xaB45c5A4B0c941a2F231C04C3f49182e1A254052`
- Gnosis Safe factory: `0xaacfeea03eb1561c4e67d661e40682bd20e3541b`

---

## 4. Cluster score (discovery & ranking only)

### 4.1 Scope — critical rule

**Cluster score is used only in these places:**

| # | Where | Purpose |
|---|--------|---------|
| 1 | **Discovery pipeline** | Weight sibling accounts when evaluating whether to **flag a parent** (with manual seed + `minSiblingCount` and other discovery rules) |
| 2 | **Alert queue ranking** | Sort incoming FUND/BIRTH/SIBLING alerts — primary sort key |
| 3 | **Sibling priority boost** | Scale Protocol 1 rank multiplier after recalculation |
| 4 | **Analytics storage** | Snapshot at alert time for later correlation (“did higher-scored clusters produce better copies?”) |

**Cluster score is NOT used for:**

- Trade entry (no threshold, no gate, no weighting)
- Exit rules
- TP/SL
- Mirror size

Trade entry depends only on **trade-level config** (`minBuyUsd`, `maxOdds`, optional tags, review mode) and the account already being under a **flagged parent**.

### 4.1.1 Formula status (v0.1.0)

The **cluster score formula is not finalized**. §4.2 documents a **candidate** shape and tunable weights for implementation scaffolding. Auto-flag thresholds (`discovery.minClusterScore`) are **unset until the formula is agreed and validated in analytics** — use **manual parent flagging** until then.

### 4.2 Per-account weight

Each sibling Polymarket account under a parent contributes `accountWeight` (not `1`).

**Vetting (default):** Only accounts with **positive realized profit** contribute. Losing siblings contribute **0** by default.

**Optional (config):** `subtractLossesFromClusterScore` — losing accounts reduce cluster score (for experimentation during analytics).

#### Factors (profit dominates)

| Factor | Description | Default behavior |
|--------|-------------|------------------|
| **Profit** | Realized PnL via cashflow reconstruction (BUY/SELL/REDEEM/MERGE), not UI `cashPnl` | Primary driver; use `log10(1 + max(profit, 0))` scaling |
| **Efficiency** | `realizedProfit / totalDeposited` into that account (cap ratio, e.g. 10×) | Strong secondary signal |
| **Win rate** | Based on **position exits**, not “resolved markets” count | **Default:** include from **first** closed position (`minExitCount: 1`). Configurable minimum. |
| **Recency** | Optional bonus for recent profitable exits | Off by default in v0.1 |

#### Candidate formula (tunable via config weights — not locked)

```
profitScore      = log10(1 + max(realizedProfit, 0)) * W_PROFIT
efficiencyScore  = min(profit / totalDeposited, EFFICIENCY_CAP) * W_EFFICIENCY
winRateScore     = max(0, winRate - 0.5) * W_WINRATE   // only if exitCount >= minExitCount

accountWeight    = profitScore + efficiencyScore + winRateScore   // if vetted (profit > 0)
                 = -lossPenalty                                   // if subtractLosses enabled and profit < 0
                 = 0                                              // default for losers

clusterScore     = sum(accountWeight for all siblings under parent)
```

Default weight ratios (starting point — **must be validated in analytics**):

- `W_PROFIT`: 10
- `W_EFFICIENCY`: 15
- `W_WINRATE`: 5
- `EFFICIENCY_CAP`: 10

### 4.3 Discovery: flagging parents

Initial Polymarket account seeds (for tracing parents) may be found via:

- High win rate (weak alone)
- Low trade volume / specialist behavior (optional)
- Recency of account creation (optional)
- Connection to known insiders (manual seed)
- **Sibling pattern:** parent with **≥ 2** linked accounts (important signal; user corrected from erroneous ≤ 2)

**Parent flagging** combines discovery rules + cluster score (when formula is locked). `discovery.minClusterScore` for auto-flag is **null / disabled in v0.1.0** until formula validation. Manual flagging and seed lists are supported from day one.

### 4.4 Alert ranking

Alerts are sorted by:

1. **`clusterScore`** (desc) — **replaces** raw parent account count as primary rank
2. Event type: **FUND** > **BIRTH**
3. Deposit size on the new account (desc)

Sibling event **priority boost** (Protocol 1): multiply base priority when parent has vetted siblings, scaled by cluster score — not a separate “2+ accounts” trade gate.

---

## 5. Protocol 1 — New account from flagged parent

| Event | What happened | Base priority | Action |
|-------|---------------|---------------|--------|
| **FUND** | Money deposited into account | High | Full watch protocol |
| **BIRTH** | Account created, little/no money | Medium | Add to watchlist only |
| **SIBLING** | New account shares flagged parent | Boost rank | Recalculate cluster score; apply priority multiplier |

### On FUND (automated)

1. **Log alert** — parent, new account, amount, timestamp, cluster score, sibling count
2. **Attach to cluster** — link account to parent graph
3. **Set state** → `WATCHING`
4. **Start scanners** (see §5.1)
5. **Do not trade** on fund alone

### On BIRTH

- Watchlist + log only; scanners light until FUND or first trade

### 5.1 Scanners (while watching or in position)

| Scanner | Watches | Action |
|---------|---------|--------|
| **Trades** | Buys & sells | Entry / primary exit |
| **Position balance** | Current share count | Reconciliation if sell missed |
| **Resolution + redeem** | Market ended, they cashed out | Close mirrored position |
| **Sibling trades** | Buy on another cluster account | **Alert only** (no auto-follow) |
| **Merge / split** | On-chain position ops | **Log only** in v0.1 |

---

## 6. Protocol 2 — Account states

```
WATCHING → SIGNAL → IN_POSITION → CLOSED
              ↘ SKIPPED
              ↘ EXPIRED
```

| State | Meaning |
|-------|---------|
| `WATCHING` | Funded/created under flagged parent; waiting for entry signal |
| `SIGNAL` | Entry rules met; pending execution or human review |
| `IN_POSITION` | Mirroring target (paper or live) |
| `CLOSED` | Exited — sell, redeem, reconciliation, TP/SL, or max hold |
| `SKIPPED` | Low confidence, wrong market, manual dismiss, or review rejected |
| `EXPIRED` | No qualifying activity within configured window |

---

## 7. Protocol 3 — Entry (trade rules)

Entry is **not** gated by cluster score. Entry applies only to accounts already tied to a **flagged parent**.

### 7.1 Entry conditions (all required unless noted)

| Rule | Config key | Default (v0.1) |
|------|------------|------------------|
| State is `WATCHING` | — | required |
| Target places **BUY** | — | required |
| Buy size ≥ minimum | `entry.minBuyUsd` | **500** USD (configurable) |
| Optional: market tag filter | `entry.marketTags` | off by default (e.g. iran, geopolitics) |
| Max entry odds (toggle) | `entry.maxOddsEnabled` + `entry.maxOdds` | **on** by default; **maxOdds = 0.5** (configurable, e.g. 0.2) |
| Review gate | `review.mode` | see §9 — default `live_only` |

### 7.2 On entry — record for analytics

Store at minimum:

- Market id, slug, title, tags
- Side (Yes/No), outcome
- Their size, price, timestamp
- Our mirrored size (after cap logic), our fill price (paper: next-poll orderbook walk — see §10)
- Parent wallet, cluster id, cluster score **at time of alert** (for analytics correlation only — not a gate)
- Latency: signal time → our entry time
- Session id, mode (paper/live), review outcome if applicable

### 7.3 Mirrored size

```
mirroredUsd = theirBuyUsd * entry.mirrorPct
if entry.mirrorCapUsd:
    mirroredUsd = min(mirroredUsd, entry.mirrorCapUsd)
```

Both `mirrorPct` and `mirrorCapUsd` are optional/configurable.

---

## 8. Protocol 4 — Exit

Poll interval while `IN_POSITION`: `exit.pollIntervalSec` (default 30–120s, configurable).

### 8.1 Target-driven exits

| Target action | Our response |
|---------------|--------------|
| Sell partial % | Sell same % of mirrored position |
| Sell 100% | Close 100% |
| Redeem after resolution | Close; record outcome |
| Buy again, same market | **Off by default** — `exit.addOnRepeatBuy` feature flag |
| Buy on sibling account | **Alert only** |

### 8.2 Position reconciliation

If we did not observe a sell but their **position balance is now zero** (or below dust threshold), treat as exit and close our mirrored position. Log as `exitReason: reconciled`.

### 8.3 Default exit behavior

**Default (v0.1.0): hold until the target exits or the market resolves** — mirror their sell/redeem/reconciliation. No TP/SL unless explicitly enabled.

### 8.4 Optional safety exits (configurable per trade & session)

| Rule | Config | Default (v0.1.0) |
|------|--------|-------------------|
| **Take profit** | `exit.takeProfitEnabled` + `exit.takeProfitPct` | **off**; when on, default +50% position PnL vs entry |
| **Stop loss** | `exit.stopLossEnabled` + `exit.stopLossPct` | **off**; when on, default -25% position PnL vs entry |
| **Max hold time** | `exit.maxHoldHours` | null (off) or 168 when enabled |
| **Slippage guard** | `exit.maxSlippagePct` | live only |
| **Auto-close on resolution** | `exit.closeOnResolution` | **true** |

**Exit priority (first match wins):**

1. Target sold / reconciled to flat / redeemed
2. TP or SL hit (only if enabled)
3. Max hold time (only if enabled)
4. Market resolved

---

## 9. Protocol 5 — Review & autonomy

`review.mode` (global default: **`live_only`**; overridable per session):

| Mode | Paper entries | Live entries |
|------|---------------|--------------|
| **`all`** | Requires human approval | Requires human approval |
| **`live_only`** (default) | Auto-execute when rules pass | Requires human approval |
| **`none`** | Auto-execute | Auto-execute |

When review is required, state stays `SIGNAL` until approved → `IN_POSITION` or rejected → `SKIPPED`.

Autonomous vs reviewed behavior is independent of `execution.mode` (`observe` / `paper` / `live`).

---

## 10. Execution modes

| Mode | Detection | Trading | Capital |
|------|-----------|---------|---------|
| `observe` | On | None | $0 |
| `paper` | On | Simulated | $0 |
| `live` | On | Real orders | User funds |

Implementation: shared strategy engine; swap **execution adapter** (paper vs live).

### 10.1 Paper fill model (default: orderbook walk at next poll)

Paper entries and exits use **`next_poll`** timing — not the signal instant price.

**On fill (buy or sell):**

1. Wait for next poll cycle after signal.
2. Fetch CLOB **order book** for the market/outcome.
3. Walk the book for our **share count** (from mirrored USD ÷ estimated price, iteratively) to compute volume-weighted average fill price.
4. Persist: raw book snapshot id, levels consumed, computed avg price, slippage vs mid.

This approximates live execution more realistically than last-trade or signal-time price.

Optional `paper.pessimisticSlippagePct` adds adverse adjustment on top of the walk.

---

## 11. Alerts (v0.1.0)

- **Dashboard** is the only alert surface in v0.1.0.
- Telegram / Discord / webhooks: deferred until channel research is done; schema should reserve `alert_channel` for future use.

---

## 12. Sessions & analytics

### 12.1 Sessions

- Every paper/live run is tagged with a **session**.
- **Private session** (default **off**): stats stay session-local; do not update global aggregates.
- Session metadata: name, created at, mode, config snapshot, private flag.

### 12.2 Global analytics

- User can **include/exclude** sessions from global stats (post-hoc edit in UI).
- Run global analytics on **all**, **selected**, or **filtered** sessions.
- Global dashboard must make inclusion toggles obvious and reversible.

### 12.3 Data to persist (analytics-first)

**Alerts**

- event type, timestamps, parent, account, amounts, cluster score snapshot, rank, scanners triggered

**Accounts & clusters**

- parent ↔ account edges, funding txs, cluster score history over time

**Trades (theirs and ours)**

- full trade lifecycle: signal → entry → exits → close reason → PnL
- config snapshot at entry (min buy, odds filter, mirror %, cap, TP/SL)

**Outcomes for tuning**

- Would-have-entered (rules matched but skipped review?)
- Hypothetical PnL at various mirror caps
- Latency distributions
- False positive labels (manual or rule-based later)

**Goal:** analytics should answer “what min buy / TP / SL / discovery threshold actually worked?” without re-running history.

---

## 13. End-to-end flow

```
DISCOVER seeds → trace PARENT → build CLUSTER (score) → FLAG parent
       ↓
SCAN flagged parents for new FUND/BIRTH
       ↓
RANK alert by clusterScore → WATCH (scanners on)
       ↓
TARGET BUY meets entry config → SIGNAL → [review?] → IN_POSITION (paper/live)
       ↓
POLL exits (sell / redeem / reconcile / TP / SL / max hold)
       ↓
CLOSED → analytics (session + optional global)
```

---

## 14. Configuration reference (summary)

```yaml
discovery:
  minSiblingCount: 2              # important pattern (>= 2 accounts from parent)
  minClusterScore: null           # disabled until formula validated; manual flag until then
  subtractLossesFromClusterScore: false
  clusterWeights:                 # candidate weights — tune via analytics
    profit: 10
    efficiency: 15
    winRate: 5
  efficiencyCap: 10
  minExitCountForWinRate: 1       # default: count from first position exit

entry:
  minBuyUsd: 500
  marketTags: []
  maxOddsEnabled: true
  maxOdds: 0.5
  mirrorPct: 1.0
  mirrorCapUsd: null

exit:
  pollIntervalSec: 60
  takeProfitEnabled: false
  takeProfitPct: 0.50             # used only when enabled
  stopLossEnabled: false
  stopLossPct: 0.25               # used only when enabled
  maxHoldHours: null              # off by default
  addOnRepeatBuy: false
  closeOnResolution: true

review:
  mode: live_only                 # all | live_only | none

execution:
  mode: paper                     # observe | paper | live

sessions:
  privateDefault: false

paper:
  fillModel: orderbook_walk_next_poll
  pessimisticSlippagePct: 0.0     # optional adverse bump after walk

alerts:
  channels: [dashboard]           # telegram/discord later
```

---

## 15. Tech stack (proposed — not locked)

| Layer | Choice |
|-------|--------|
| Language | Python (ingestion, scoring, strategy) |
| Database | PostgreSQL |
| API | FastAPI (dashboard backend) |
| Frontend | TBD with user (next design pass) |
| Chain | Polygon RPC (Alchemy/QuickNode); Data API + Gamma for enrichment |
| Jobs | Scheduled + event-driven watchers |

---

## 16. Implementation phases

| Phase | Deliverable |
|-------|-------------|
| **0** | Manual trace of 2–3 known cluster wallets; validate funding graph |
| **1** | Postgres schema + config + alert log + cluster score (discovery only) |
| **2** | Parent scanner (FUND/BIRTH) + watch scanners |
| **3** | Paper execution adapter + state machine + TP/SL |
| **4** | Sessions + analytics API + inclusion toggles |
| **5** | Dashboard UI |
| **6** | Live execution adapter (behind flag) |

---

## 17. Open questions

| # | Question | Notes |
|---|----------|-------|
| 1 | Finalize `clusterScore` formula and weights | Candidate in §4.2; validate in analytics before `minClusterScore` |
| 2 | Market tag / Layer D weighting | Deferred |
| 3 | Manual false-positive labels in dashboard | v0.1 or v0.2? |
| 4 | RPC provider budget | Affects poll frequency |
| 5 | Telegram vs other alert channels | User researching |

---

## 18. Document history

| Version | Changes |
|---------|---------|
| v0.1.0 | PolyCrawler repo bootstrap; locked v0.1 defaults (minBuy 500, maxOdds 0.5 on, TP/SL off, orderbook walk fills, dashboard-only alerts, cluster score application table, formula still candidate |
| v0.1 | Initial spec from design sessions |
