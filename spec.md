# PolyCrawler — Product & Technical Spec (v0.1.5)

> Living document. Source of truth for behavior, protocols, and analytics requirements.
> Repository: **PolyCrawler**

---

## 1. Purpose

Build a system that:

1. **Finds** Polymarket accounts likely connected to the same real-world operator (“parent” funding wallet + sibling accounts).
2. **Watches** new accounts funded by already-flagged parents **before they win** (ideally on first deposit).
3. **Mirrors cluster net exposure** in **paper mode first** (no money required), then optionally live.
4. **Records rich analytics** so entry/exit rules, scoring weights, and thresholds can be tuned from real data.

**Core product sentence:** When money from a parent we already care about lands in a new Polymarket account, watch the cluster; when the cluster has net exposure in a market, mirror it (paper or live); when cluster net goes flat, hedged, or resolved, we exit; log everything for accuracy testing before risking capital.

**Non-goals for v0.1:** Perfect insider conviction, legal classification, beating Chainalysis/PolyInsider on generic fresh-wallet alerts.

---

## 2. Glossary

| Term | Meaning |
|------|---------|
| **Parent wallet** | On-chain address that funds Polymarket accounts (EOA, CEX withdrawal path, etc.). Primary identity anchor for clustering. |
| **Polymarket account** | A tradable address on Polymarket - We can track methods: deposit wallet, Safe, or proxy. |
| **Sibling** | Another Polymarket account funded by the same parent wallet. |
| **Cluster** | Parent + all linked Polymarket accounts + their derived scores. |
| **Cluster score** | Weighted quality of a cluster. Used **only** for discovery, flagging, and alert **ranking** — **not** for trade entry. |
| **Flagged parent** | Parent that met discovery criteria and is on the watchlist. |
| **Paper trade** | Simulated fill; no wallet or capital required. |
| **Session** | A bounded run of paper/live activity with its own stats. |
| **Global analytics** | Aggregated stats across selected sessions (configurable inclusion). |
| **Sell** | Closing/reducing a position on the order book before resolution. |
| **Redeem** | Cashing out winning shares after a market **resolved** (not a normal sell). |
| **Merge / split** | On-chain ops converting USDC ↔ outcome token pairs. v0.1: log only, no auto-trade. |
| **Position reconciliation** | If sibling share balances drop but we missed sell events, close or adjust our mirrored position to match cluster net. |
| **Net exposure** | Per market, per cluster: (sum of Yes shares across siblings) − (sum of No shares across siblings). Positive = net Yes; negative = net No. |
| **Net cluster mirroring** | Mirror the cluster’s net exposure (not a single account). Position size = `net × mirrorPct`, capped by `mirrorCapUsd`; adjust on each net change. |
| **CONFLICT alert** | Two or more siblings hold opposing sides of the same market (both above dust). Always logged when `conflict.always_alert` is true. |
| **CONFLICT_RESOLVED alert** | Opposing sibling overlap ended — net within dust or one side flat. |
| **Follow re-entry** | Cluster net was ~flat, then becomes non-zero again within `reentryWindowMinutes` — mirror as new entry if rules pass (§7.6). |

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

Trade entry depends on **cluster-level** trade config (`minBuyUsd`, `maxOdds`, optional tags, review mode) and the cluster being tied to a **flagged parent** — not on mirroring a single account.

### 4.1.1 Formula status (v0.1.1)

The cluster score formula is **experimental**. Implement **variant B (sqrt)** as the runtime default; ship a validation script that computes **A (log), B (sqrt), and C (piecewise)** on ~20 labeled wallets (10 suspicious, 10 normal) before enabling `discovery.minClusterScore`.

**v0.1 build order:** manual parent seed first; auto-discovery after trading engine is proven (see §16).

Auto-flag: use `discovery.minSiblingCount` until `minClusterScore` is validated; when `minClusterScore` is set, it **overrides** `minSiblingCount`.

### 4.2 Per-account weight

Each sibling Polymarket account under a parent contributes `accountWeight` (not `1`).

**Vetting (default):** Only accounts with **positive realized profit** contribute. Losing siblings contribute **0** by default.

**Optional (config):** `subtractLossesFromClusterScore` — losing accounts reduce cluster score (for experimentation during analytics).

#### Factors (profit dominates)

| Factor | Description | Default behavior |
|--------|-------------|------------------|
| **Profit** | Realized PnL via cashflow reconstruction (BUY/SELL/REDEEM/MERGE), not UI `cashPnl` | Primary driver; use `log10(1 + max(profit, 0))` scaling |
| **Efficiency** | `realizedProfit / totalDeposited` into that account (cap ratio, e.g. 10×) | Strong secondary signal |
| **Win rate** | **Profitable exits ÷ total exits** (position exit events, not resolved-market count) | **Default:** `minExitCount: 1` (count from first exit). Configurable minimum. |
| **Recency** | Optional bonus for recent profitable exits | Off by default in v0.1 |

#### Profit score variants (implement all in validation script; **B is runtime default**)

```python
# A) Log — compresses large profits
profitScore = log10(1 + max(profit, 0)) * W_PROFIT


# B) Square root — less compression (DEFAULT runtime)
profitScore = sqrt(max(profit, 0)) * W_PROFIT


# C) Piecewise — linear up to 10k, log after
if profit <= 10000:
    profitScore = (profit / 1000) * (W_PROFIT / 10)
else:
    profitScore = 10 * (W_PROFIT / 10) + log10(profit / 10000) * 5
```

Shared components:

```
efficiencyScore  = 0  if totalDeposited <= 0
                 = min(profit / totalDeposited, EFFICIENCY_CAP) * W_EFFICIENCY  otherwise
winRateScore     = max(0, winRate - 0.5) * W_WINRATE   // winRate = profitable_exits / total_exits
                   // only if exitCount >= minExitCount

accountWeight    = profitScore + efficiencyScore + winRateScore   // if vetted (profit > 0)
                 = -lossPenalty                                   // if subtractLosses enabled and profit < 0
                 = 0                                              // default for losers

clusterScore     = sum(accountWeight for all siblings under parent)
```

Default weights (tune via backtests):

- `W_PROFIT`: 2 (sqrt variant), `W_EFFICIENCY`: 15, `W_WINRATE`: 5, `EFFICIENCY_CAP`: 10
- `discovery.profitFormula`: `sqrt` | `log` | `piecewise`

**Recalc policy:** Recompute `clusterScore` after any sibling **position close**; update alert ranks for open watch items on that parent.

### 4.3 Discovery: flagging parents

Initial Polymarket account seeds (for tracing parents) may be found via:

- High win rate (weak alone)
- Low trade volume / specialist behavior (optional)
- Recency of account creation (optional)
- Connection to known insiders (manual seed)
- **Sibling pattern:** parent with **≥ 2** linked accounts 

**Parent flagging rules:**

```yaml
discovery:
  minSiblingCount: 2       # auto-flag parent with >= 2 linked accounts (simple rule)
  minClusterScore: null    # when set, overrides minSiblingCount
  fundingHops: 3           # max hops tracing funding on Polygon network
```

Manual seed list always supported. Parents with `is_ignored: true` are excluded from watch and ranking.

### 4.4 Alert ranking

Alerts are sorted by:

1. **`clusterScore`** (desc) — primary rank (replaces raw account count)
2. Event type: **FUND** > **BIRTH**
3. Deposit size on the new account (desc)
4. **`alert_time` ASC** — tie-breaker (earlier first)

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
3. **Add account to cluster watchlist** — scanners include this sibling (§5.1); no trade on fund alone
4. **Start scanners** (see §5.1)

### On BIRTH

- Watchlist + log only; scanners light until FUND or first trade

### 5.1 Scanners (cluster watch)

All scanners feed **cluster net** recalculation (§7.7). Position lifecycle state is **per cluster × market** (§6).

| Scanner | Watches | Action |
|---------|---------|--------|
| **Trades** | Any sibling buy, sell, redeem | Recalc net → entry signal or `net_adjustment` mirror |
| **Position balance** | All sibling share counts per market | Reconciliation if trade events missed (§8.2) |
| **Resolution + redeem** | Market ended; sibling redeemed | Recalc net → close mirrored position if net flat |
| **Sibling overlap** | Opposing sibling balances | `CONFLICT` / `CONFLICT_RESOLVED` alerts (§7.7) |
| **Merge / split** | On-chain position ops | **Log only** in v0.1 |

---

## 6. Protocol 2 — Position state machine

Mirroring lifecycle is **per `(clusterId, marketId)`**, not per account. Siblings only add **watchlist coverage** (§5); they do not get their own `IN_POSITION`.

### 6.1 Two layers (do not confuse)

| Layer | What it tracks | Example |
|-------|----------------|---------|
| **Cluster watch** | Flagged parent + all siblings; scanners always on | Parent `0xABC` has 3 funded accounts |
| **Cluster position** | One state machine row per **market** the cluster touches | Cluster `0xABC` × market `will-x-win` |

An account **FUND** does **not** create a position state — it adds a sibling to the cluster watchlist. A **`cluster_positions`** row is created **lazily** on **first activity** in a market (first sibling trade or non-zero balance on poll).

### 6.2 States

```
                    ┌─────────────────────────────────────┐
                    │            WATCHING                  │
                    │  No mirrored hold (flat / idle)      │
                    └──────────────┬──────────────────────┘
                                   │
           entry rules pass        │        entry rules pass + no review
           + review required       │        (paper/live auto)
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             ┌────────────┐                 ┌─────────────┐
             │   SIGNAL   │                 │ IN_POSITION │
             └─────┬──────┘                 └──────┬──────┘
          approve │ reject                       │
                  │    └────────► SKIPPED        │ net deltas (stay)
                  ▼                              │ net ~0 / TP / SL / resolve
            ┌─────────────┐                      ▼
            │ IN_POSITION │◄─────────────  ┌───────────┐
            └──────┬──────┘                │  CLOSED   │
                   │                       └─────┬─────┘
                   └──────────────────────────►│ auto → WATCHING
                                                 (end of cycle)
```

| State | Meaning |
|-------|---------|
| `WATCHING` | No mirrored position in this market. Cluster net ~0 **or** we closed and reset. May carry `tp_sl_mirror_suspended_until_flat` after a TP/SL exit (§6.4). |
IN_POSITION` | Actively mirroring cluster net (§7.7). |
| `CLOSED` | **Bookkeeping only — not a resting state.** We exited our mirror this cycle (hedge, TP, SL, redeem, etc.). The processor logs `exitReason`, PnL, and `last_closed_at`, then **immediately** sets state back to `WATCHING` on the **same poll tick**. You never “sit” in `CLOSED`; it exists so every exit is a recorded event before the row returns to idle. |
| `WATCHING` | No mirrored position in this market. Cluster net ~0 **or** we closed and reset. May carry `tp_sl_mirror_suspended_until_flat` after a TP/SL exit (§6.4). |











| `WATCHING` | No mirrored position in this market. Cluster net ~0 **or** we closed and reset. May carry `tp_sl_mirror_suspended_until_flat` after a TP/SL exit (§6.4)
| `siblingBalances` | Map `accountId → { yesShares, noShares }` |
| `net_exposure` | Signed shares: sum(Yes) − sum(No) |
| `last_known_net` | Previous net for delta mirroring |
| `mirrored_shares` | Our current Yes/No hold (or signed net hold) |
| `last_closed_at` | For `followReentryAfterSell` (§7.6) |
| `tp_sl_mirror_suspended_until_flat` | Set **only** on `tp_hit` / `sl_hit`. While true: do not re-enter or resume mirroring until cluster net ~0, then clear flag (§6.4). |

### 6.4 Event processor (each poll batch)

Process sibling events in **timestamp order**, then run reconciliation (§8.2). For each affected `(cluster, market)`:

**1. Update balances → net**

- Apply `entry.hedgeFilterMode` (§7.5) when translating **trade events** into balance deltas.
- Reconciliation **overwrites** balances from Data API — always wins over event path.

**2. `IN_POSITION`**

- Mirror net delta (§7.7).
- If net → ~0: → `CLOSED` (`cluster_hedged`).
- Else check exit priority (§8.4): TP, SL, max hold, resolution → `CLOSED` with reason.

**3. `WATCHING`**

- If `tp_sl_mirror_suspended_until_flat` and net ~0: clear flag.
- If net non-zero, **not** `tp_sl_mirror_suspended_until_flat`, and §7.1 entry rules pass:
  - Review required → `SIGNAL`
  - Else → execute entry → `IN_POSITION`
- If `followReentryAfterSell` (§7.6): recent `last_closed_at` + net ~0 → non-zero within window uses same entry path.

**4. `SIGNAL`**

- Review approved → fill at next poll → `IN_POSITION`.
- Review rejected → `SKIPPED`.
- Optional timeout → `EXPIRED` (§6.5).

**5. `SKIPPED`**

- If net ~0 → `WATCHING`.
- Else remain `SKIPPED` (cluster has exposure but we chose not to mirror).

**6. `CLOSED`**

- Persist close reason, PnL, analytics.
- Set `last_closed_at`; if reason is `tp_hit` or `sl_hit`, set `tp_sl_mirror_suspended_until_flat: true`.
- → `WATCHING` (same processor tick — see `CLOSED` in §6.2).

### 6.5 Optional timeouts

```yaml
position:
  signalExpireMinutes: null      # SIGNAL → EXPIRED if no review; null = off
  marketWatchExpireDays: null    # WATCHING with activity but no entry; null = off
```

### 6.6 Account watchlist (not the position FSM)

Accounts under a flagged parent have **`watchStatus`** for discovery hygiene only:

| watchStatus | Meaning |
|-------------|---------|
| `active` | Funded / trading; included in cluster polls |
| `expired` | No trades within `watch.accountExpireDays` of fund (configurable; optional) |

`watchStatus: expired` does **not** remove the account from the graph — a new trade reactivates polling. It does **not** map to `cluster_positions` states.

---

## 7. Protocol 3 — Entry (trade rules)

Entry is **not** gated by cluster score. Entry applies when a **flagged parent’s cluster** develops non-zero net exposure in a market.

### 7.1 Entry conditions (all required unless noted)

Evaluated on **cluster net** after processing all sibling events in the poll batch (**timestamp order**).

| Rule | Config key | Default (v0.1) |
|------|------------|------------------|
| Cluster position state is `WATCHING` and not `tp_sl_mirror_suspended_until_flat` | — | required |
| Cluster position state is not `SKIPPED` | — | required |
| Cluster net becomes non-zero (above `conflict.min_net_usd`) | — | required |
| \|net\| USD ≥ minimum | `entry.minBuyUsd` | **500** USD (configurable) |
| Optional: market tag filter | `entry.marketTags` | `[]` = **all markets qualify**; non-empty = allow-list only |
| Max entry odds (toggle) | `entry.maxOddsEnabled` + `entry.maxOdds` | **on**; **maxOdds = 0.5** — applied to the **trade that moved net** (price of the outcome bought) |
| Review gate | `review.mode` | see §9 — default `live_only` |

If cluster net is **already non-zero** and mirrored (`IN_POSITION`), sibling trades only produce **`net_adjustment`** mirrors — entry rules are **not** re-applied.

### 7.2 On entry / adjustment — record for analytics

Store at minimum:

- Market id, slug, title, tags
- Cluster id, parent wallet, cluster score **at time of event** (analytics only — not a gate)
- `net_exposure` before / after, `net_delta`, side implied by delta (Yes/No)
- `source_sibling` account id, their trade size, price, timestamp
- `event_type`: `entry` | `net_adjustment` | `exit`
- Our mirrored size (after cap), fill price (paper: next-poll orderbook walk — §10)
- Latency: signal time → our fill time
- Session id, mode (paper/live), review outcome if applicable

### 7.3 Mirrored size

Cluster net drives size (§7.7):

```
targetShares = sign(net) × min(abs(net) × entry.mirrorPct, capShares)
```

`capShares` = `entry.mirrorCapUsd` at current mid (or last trade). Trade the delta vs current hold each cycle.

Both `mirrorPct` and `mirrorCapUsd` are optional/configurable.

### 7.4 Post-entry fast polling

After entry (`IN_POSITION`), poll at higher frequency before reverting to normal exit interval:

```yaml
entry:
  postEntryPollIntervalSec: 10   # default
  postEntryPollCount: 6          # 6 × 10s = 1 minute fast window
```

Catches immediate sells and improves orderbook-walk fill timing right after entry.

### 7.5 Intra-fill hedges (both Yes and No in one transaction)

#### What this is solving

Sometimes **one wallet** buys **both Yes and No** in a **single fill** — misclick, UI quirk, arb, or intentional straddle. That is different from **cross-sibling** hedging (Alice Yes, Bob No), which cluster net already handles in §7.7.

§7.5 only asks: **when one fill has two legs, do we sanitize it before updating balances, or let the math net it?**

```yaml
entry:
  hedgeFilterMode: net_only          # net_only | filter_before_net
  ignoreHedgeTrades: true            # only when filter_before_net
  hedgeDominantThreshold: 2.0        # only when filter_before_net
```

#### Mode: `net_only` (default)

**Pipeline:** each leg updates that sibling’s Yes/No balance → **cluster net = sum(Yes) − sum(No)**.

No special “this fill looks hedgy” branch.

Example:

```
Alice one fill: +800 Yes, +200 No
→ Alice balance: 800 Yes, 200 No
→ Cluster net: +600 Yes
→ Mirror delta per §7.7
```

**Why default:**

- One rule: balances in, net out — same as reconciliation.
- Consistent with cluster architecture (opposing exposure nets, including within one wallet).
- Simpler state machine event path (§6.4).
- `conflict.min_net_usd` already ignores dust-level net.

**Reconciliation** (balance poll) is **authoritative** if trade parsing and on-chain balances disagree.

#### Mode: `filter_before_net`

**Pipeline:** inspect **each fill** before applying balance deltas:

- If one side’s USD **> `hedgeDominantThreshold` ×** the other → apply **dominant leg only**.
- Else → **ignore the entire fill** (no balance update from that event).
- Then compute cluster net from balances.

Same fill as above:

```
+800 Yes, +200 No → dominant Yes (>2×) → only +800 Yes counted → net +800 (not +600)
```

Near tie:

```
+500 Yes, +450 No → neither > 2× → fill ignored → net unchanged
(net_only would yield +50 Yes net)
```

#### When the modes agree vs diverge

| Scenario | `net_only` | `filter_before_net` |
|----------|------------|---------------------|
| One-sided buy (+1000 Yes only) | +1000 net | Same |
| Dominant hedge (+800 Yes, +200 No) | +600 net | **+800 net** |
| Near 50/50 (+500 Yes, +450 No) | +50 net | **0** (fill ignored) |
| Alice hedged fill + Bob +100 Yes | Net from all balances | Alice’s fill filtered; Bob same |
| Two separate txs (Yes then No) | Net from both | Each tx filtered separately — can diverge more |
| Reconciliation poll | **Truth wins** | **Truth wins** |

Both modes should **converge on reconciliation**. The toggle mainly affects **event-driven updates between polls** (entry timing, paper fill on signal poll).

#### When to use `filter_before_net`

Turn on only if paper/backtests show **near-50/50 single fills** causing unwanted micro-entries (net briefly crosses `minBuyUsd`, then reconciliation flattens). Treat as a **noise knob**, not core architecture.

**Cost of `filter_before_net`:** event-derived balances can **temporarily disagree** with reconciliation; next poll may **jump** if a filtered fill actually landed on-chain.

#### State machine interaction (§6.4)

```
net_only:           trade event → update each leg → recompute net → FSM transition

filter_before_net:  trade event → hedge filter → update balance → recompute net → FSM
                    poll          → overwrite balances from API → recompute net → FSM
```

Prefer **`net_only`** so the event path and reconciliation path share the same shape.

---

### 7.6 Follow re-entry after flat net

**Not** a cooldown that blocks re-entry. When enabled, if **cluster net** was ~0 (within `conflict.min_net_usd`) and becomes non-zero again within the window, treat as **new entry** (subject to §7.1 rules).

```yaml
entry:
  followReentryAfterSell: true   # default on
  reentryWindowMinutes: 5        # net must go from ~0 to non-zero within this window after going flat
```

Per-account sell-then-buy round-trips that **do not change cluster net** do **not** trigger re-entry. When `followReentryAfterSell` is on, it overrides `exit.addOnRepeatBuy` being false for that re-entry.

### 7.7 Sibling positions — net cluster mirroring

Siblings share the same parent funding wallet; the cluster is **one trading entity** for mirroring.

```yaml
conflict:
  policy: net_cluster_position   # alert_only retained as manual fallback only
  min_net_usd: 100               # |net| below this (USD) treated as zero
  dust_shares: 0.001             # float noise for balance comparisons
  always_alert: true             # log CONFLICT even when actively mirroring net
```

#### Policy: `alert_only` (manual fallback)

- Log **`CONFLICT`** on opposing sibling balances; **no** automatic mirroring or net adjustments.
- For normal paper/live runs, use `net_cluster_position`.

#### Policy: `net_cluster_position` (default)

**Per cluster, per market, maintain:**

- `net_exposure` — signed share count (positive = net Yes, negative = net No)
- `last_known_net` — for delta calculation
- Sibling balance map — each account’s Yes/No shares; updated every poll or trade event

**Target mirrored position:**

```
targetShares = sign(net) × min(abs(net) × entry.mirrorPct, capShares)
```

`capShares` is `entry.mirrorCapUsd` converted at current mid (or last trade) price. Recompute target each cycle; trade the delta vs current hold.

**On any sibling buy, sell, or redeem:**

1. Update that sibling’s balance (redeem → zero that position).
2. Recalculate `net_exposure`.
3. `delta = new_net − old_net`.
4. If `abs(delta)` above dust: mirror `delta × mirrorPct` (subject to cap).
   - `delta > 0` → increase net Yes exposure (buy Yes).
   - `delta < 0` → increase net No exposure (buy No, or reduce Yes — no shorting).
5. Record trade with reason `net_adjustment` and `source_sibling` account id.

Process events in **timestamp order** within a poll window.

**Edge cases:**

| Case | Behavior |
|------|----------|
| Net → 0 (within `min_net_usd`) | Close entire mirrored position; `exitReason: cluster_hedged` |
| Net flips sign (e.g. +100 Yes → −50 No) | Two legs: exit full Yes, then enter No — one adjustment event, two fills |
| Cap reached | Do not increase further while net grows; **may** reduce when net shrinks |
| First non-zero net | Entry subject to §7.1 (cluster net USD, odds on trade that moved net) |
| Net already non-zero, sibling adds same side | Mirror delta only; do not re-apply entry rules |
| Overlapping opposing balances | Log **`CONFLICT`** (if `always_alert`); still mirror net |
| Overlap ends | Log **`CONFLICT_RESOLVED`** |

**After TP/SL close:** set `tp_sl_mirror_suspended_until_flat`. Do not re-enter or resume mirroring until cluster net ~0 (clears flag), then allow fresh entry per §7.1 / §7.6. Other close reasons (hedge, redeem, resolution) do **not** set this flag.

**Alerts:** include net exposure, each sibling’s balance, market id, parent, cluster id.

---

## 8. Protocol 4 — Exit

Poll interval while cluster position is `IN_POSITION`: `exit.pollIntervalSec` (default 30–120s, configurable).

NOTE FOR 8 AND 8.1
 -  using polling intervals instead of real-time exit detection through RTDS and websocket stuff causes delays and possibility to miss events entirely
    - note that missing events case is patched up in our case with the position reconciliation...

### 8.1 Cluster-net exits

All exits are driven by **cluster net changes** (§7.7), not per-account partial sells.

| Cluster net change | Our response |
|--------------------|--------------|
| Net delta (any sibling buy/sell) | Mirror `delta × mirrorPct` (subject to cap); reason `net_adjustment` |
| Net → ~0 (`min_net_usd`) | Close entire mirrored position; `exitReason: cluster_hedged` |
| Net flips sign | Two legs: exit old side, enter new side |
| Sibling redeems after resolution | Recalc net → close if net flat; record outcome |
| Net ~0 then non-zero within re-entry window | New entry if §7.1 + §7.6 pass |
| Repeat buy (notify only) | `exit.notifyOnRepeatBuy: true` — dashboard notice when net unchanged |

Optional safety exits (§8.4) apply to the **mirrored cluster position** as a whole.

### 8.2 Position reconciliation

Each poll, rebuild **all sibling balances** per market from Data API (or RPC batch). Recompute cluster net.

If net changed vs `last_known_net` but we missed trade events, mirror the implied delta (same rules as §7.7).

Log: `exitReason: reconciled` when net goes to ~0; include old vs new net, per-sibling balances.

### 8.3 Default exit behavior

**Default (v0.1):** hold until **cluster net** is flat/hedged, siblings redeem, reconciliation catches up, or the market resolves. No TP/SL unless explicitly enabled.

### 8.4 Optional safety exits (configurable per trade & session)

| Rule | Config | Default (v0.1.0) |
|------|--------|-------------------|
| **Take profit** | `exit.takeProfitEnabled` + `exit.takeProfitPct` | **off**; when on, default +50% position PnL vs entry |
| **Stop loss** | `exit.stopLossEnabled` + `exit.stopLossPct` | **off**; when on, default -25% position PnL vs entry |
| **Max hold time** | `exit.maxHoldHours` | null (off) or 168 when enabled |
| **Slippage guard** | `exit.maxSlippagePct` | live only |
| **Auto-close on resolution** | `exit.closeOnResolution` | **true**; source: **Data API `isResolved`** (not heuristic alone) |

**Exit priority (first match wins):**

1. Cluster net flat / hedged / redeemed (incl. reconciliation)
2. TP or SL hit on mirrored position (**skipped when disabled**)
3. Max hold time (**skipped when disabled**)
4. Market resolved per Data API

---

## 9. Protocol 5 — Review & autonomy

`review.mode` (global default: **`live_only`**; overridable per session):

| Mode | Paper entries | Live entries |
|------|---------------|--------------|
| **`all`** | Requires human approval | Requires human approval |
| **`live_only`** (default) | Auto-execute when rules pass | Requires human approval |
| **`none`** | Auto-execute | Auto-execute |

When review is required, cluster position state stays `SIGNAL` until approved → `IN_POSITION` or rejected → `SKIPPED`.

Autonomous vs reviewed behavior is independent of `execution.mode` (`observe` / `paper` / `live`).

---

## 10. Execution modes

| Mode | Detection | Trading | Capital |
|------|-----------|---------|---------|
| `observe` | On | None | $0 |
| `paper` | On | Simulated | $0 |
| `live` | On | Real orders | User funds |

Implementation: shared strategy engine; only swap **execution adapter** (paper vs live).

### 10.1 Paper fill model (default: orderbook walk at next poll)

Paper entries and exits use **`next_poll`** timing — not the signal instant price.

**On fill (buy or sell):**

1. Wait for next poll cycle after signal.
2. Fetch CLOB **order book** for the market/outcome.
3. Walk the book for our **share count** (from mirrored USD ÷ estimated price, iteratively) to compute volume-weighted average fill price.
    - round down for # of shares if decimal...
4. Persist: raw book snapshot id, levels consumed, computed avg price, slippage vs mid.

This approximates live execution more realistically than last-trade or signal-time price.

Optional `paper.pessimisticSlippagePct` adds adverse adjustment on top of the walk.

---

## 11. Alerts (v0.1.0)

- **Dashboard** is the only alert surface in v0.1.0.
- Trade / protocol alerts include **`CONFLICT`** and **`CONFLICT_RESOLVED`** (§7.7) when sibling opposing positions start or end.
- Telegram / Discord / webhooks: deferred until channel research is done; schema should reserve `alert_channel` for future use.

---

## 12. Sessions & analytics

### 12.1 Sessions

- Every paper/live run is tagged with a **sessionID**.
    - based off date start and length probably, exact way to generate TBD
- **Private session** (default **off**): stats are temporary, Private sessions are not saved to sesions for analytics
- Session metadata: name, created at, mode, config snapshot, private flag.

### 12.2 Global analytics

- User can **include/exclude** sessions from global stats (post-hoc edit in UI).
- Run global analytics on **all**, **selected**, or **filtered** sessions.
- Global dashboard must make inclusion toggles obvious and reversible.

Actual analytics to be done is still being brainstormed rn but wel think something up for the next version.

### 12.3 Data to persist (analytics-first)

**Alerts**

- event type, timestamps, parent, account, amounts, cluster score snapshot, rank, scanners triggered

**Accounts & clusters**

- parent ↔ account edges, funding txs, cluster score history over time

**Trades (theirs and ours)**

- Full lifecycle per **cluster × market**: `entry` → `net_adjustment`(s) → `exit` → close reason → PnL
- Each leg: `source_sibling`, `net_before`, `net_after`, our fill details
- Config snapshot at entry (min buy, odds filter, mirror %, cap, TP/SL)

**Outcomes for tuning**

- Would-have-entered (rules matched but skipped review?)
- Hypothetical PnL at various mirror caps
- Latency distributions
- **False positive labels** — dashboard button in v0.1 (`alerts.is_false_positive`)

**Goal:** analytics should answer “what min buy / TP / SL / discovery threshold actually worked?” without re-running history.

---

## 13. End-to-end flow (v0.1 build order)

```
MANUAL parent seed (5–10 wallets from research)
       ↓
PARENT watcher → FUND/BIRTH on seeded parents only
       ↓
RANK by clusterScore → WATCH cluster (scanners on all siblings)
       ↓
Sibling trade(s) → cluster net ≠ 0, entry rules pass → SIGNAL → [review?] → IN_POSITION (paper)
       ↓
FAST post-entry polls → normal polls → net deltas / hedge flat / redeem / reconcile / resolution
       ↓
CLOSED → analytics (session + optional global)
       ↓
(later) AUTO-DISCOVERY + backtests to tune cluster score
```

---

## 14. Configuration reference (summary)

```yaml
discovery:
  minSiblingCount: 2
  minClusterScore: null           # overrides minSiblingCount when set
  fundingHops: 3
  profitFormula: sqrt             # sqrt | log | piecewise
  subtractLossesFromClusterScore: false
  clusterWeights:
    profit: 2
    efficiency: 15
    winRate: 5
  efficiencyCap: 10
  minExitCountForWinRate: 1

entry:
  minBuyUsd: 500
  marketTags: []                  # empty = all markets qualify
  maxOddsEnabled: true
  maxOdds: 0.5
  mirrorPct: 1.0
  mirrorCapUsd: null
  postEntryPollIntervalSec: 10
  postEntryPollCount: 6
  hedgeFilterMode: net_only         # net_only | filter_before_net
  ignoreHedgeTrades: true           # filter_before_net only
  hedgeDominantThreshold: 2.0       # filter_before_net only
  followReentryAfterSell: true
  reentryWindowMinutes: 5

exit:
  pollIntervalSec: 60
  takeProfitEnabled: false
  takeProfitPct: 0.50
  stopLossEnabled: false
  stopLossPct: 0.25
  maxHoldHours: null
  addOnRepeatBuy: false
  notifyOnRepeatBuy: true
  closeOnResolution: true
  resolutionSource: data_api_isResolved
  tpSlSuspendMirrorUntilFlat: true   # on tp_hit/sl_hit, set tp_sl_mirror_suspended_until_flat until net ~0

review:
  mode: live_only

execution:
  mode: paper

sessions:
  privateDefault: false

paper:
  fillModel: orderbook_walk_next_poll
  pessimisticSlippagePct: 0.0

conflict:
  policy: net_cluster_position   # alert_only | net_cluster_position
  min_net_usd: 100
  dust_shares: 0.001
  always_alert: true

position:
  signalExpireMinutes: null
  marketWatchExpireDays: null

watch:
  accountExpireDays: null        # optional; account watchStatus → expired

alerts:
  channels: [dashboard]

retention:
  rawTradesDays: 90
  analyticsIndefinite: true
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
| RPC batching | `web3.py` + multicall for balance checks across watched accounts |
| RPC logging | `rpc_usage` table — timestamp, method, latency, optional compute units |

---

## 16. Implementation phases (revised)

| Order | Phase | Deliverable |
|-------|-------|-------------|
| 1 | **Manual seed** | Hand-pick 5–10 parents from Iran research |
| 2 | **Parent watcher** | FUND/BIRTH for seeded parents only |
| 3 | **Paper engine** | Cluster×market state machine, net mirroring, entry/exit, fast post-entry polls, orderbook walk |
| 4 | **Reconciliation + RPC batch** | Balance multicall, reconciliation scanner, usage logs |
| 5 | **Dashboard** | Alerts, paper positions, false-positive button, sessions |
| 6 | **Backtesting** | Dune for initial formula tuning; Data API local store for ongoing replays |
| 7 | **Auto-discovery** | Cluster score auto-flag after engine is proven |
| 8 | **Live** | Execution adapter behind flag |

---

## 17. Backtesting (§19)

- Replay historical scenarios against watcher + paper trader.
- Compare hypothetical PnL under configs (`minBuyUsd`, `maxOdds`, cluster weights, discovery thresholds).
- **Data sources:** Dune first for formula validation; Data API ingested locally for ongoing backtests.
- Store runs as sessions with `mode: backtest`.
- Validation script: score variants A/B/C on ~20 labeled wallets before enabling `minClusterScore`.

---

## 18. Data retention

| Data | Retention |
|------|-----------|
| Raw trade / poll logs | 90 days (configurable `retention.rawTradesDays`) |
| Analytics aggregates, paper PnL, session summaries | Indefinite |
| RPC usage logs | 90 days default |

---

## 19. Schema sketch (next implementation step)

Core tables: `parents` (`is_ignored`), `accounts` (`watch_status`), `clusters`, `cluster_positions` (`state`, `net_exposure`, `mirrored_shares`, `sibling_balances` json, `tp_sl_mirror_suspended_until_flat`, `last_closed_at`), `sibling_balance_snapshots` (per poll), `alerts` (`is_false_positive`), `paper_trades`, `sessions`, `rpc_logs`, `backtest_runs`, `config_snapshots`.

---

## 20. Open questions

| # | Question | Status |
|---|----------|--------|
| 1 | Market tag / Layer D weighting | Deferred |
| 2 | Sibling opposing-side policy beyond CONFLICT alert | **Resolved** — `net_cluster_position` default (§7.7) |
| 3 | RPC provider budget | TBD |
| 4 | Telegram / external alerts | User researching |
| 5 | Cluster×market state machine | **Resolved** — §6 |
| 6 | Entry `minBuyUsd` / `maxOdds` on cluster net after poll batch | **Resolved** — §7.1 |
| 7 | `hedgeFilterMode` — `net_only` vs `filter_before_net` for both-sides fills | **Resolved** — default `net_only` (§7.5) |
| 8 | `followReentryAfterSell` under net mirroring | **Resolved** — cluster net ~0 → non-zero (§7.6) |
| 9 | Per-account exit rows vs net-delta | **Resolved** — cluster-net only (§8.1) |

---

## 21. Document history

| Version | Changes |
|---------|---------|
| v0.1.5 | `CLOSED` clarified (§6.2); rename → `tp_sl_mirror_suspended_until_flat`; §7.7 TP/SL wording aligned |
| v0.1.4 | Full cluster×market state machine (§6); expanded §7.5 hedge modes; `position` / `watch` config |
| v0.1.3 | Cluster-centric entry (§7.1), exits (§8), re-entry (§7.6), analytics/schema; `hedgeFilterMode` default `net_only` (§7.5); §6 redesign flagged; #6–#9 resolved |
| v0.1.2 | Net cluster position mirroring (§7.7); `conflict` config; sibling scanner/exit updates; open questions 5–9 for remaining ambiguities |
| v0.1.1 | Decisions from design review: sqrt default + A/B/C validation script; manual seed first; post-entry fast polls; follow re-entry; hedge 2×; backtesting; RPC batching; reconciliation detail; false-positive v0.1; revised build order |
| v0.1.0 | Repo bootstrap; core protocols and defaults |
| v0.1 | Initial design sessions |
