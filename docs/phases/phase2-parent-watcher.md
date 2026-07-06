# Phase 2 — Parent Watcher + Scoring

**Status:** ⬜ Not started
**Prerequisites:** [Phase 1](phase1-manual-seed.md) complete
**Human-readable docs:** [account-types.md](../overview/account-types.md), [clustering.md](../discovery/clustering.md), [new-account-detection.md](../discovery/new-account-detection.md)

---

## Goal

Build the ingestion layer: poll Polygon for FUND/BIRTH events on seeded parents, detect new sibling accounts, and compute cluster scores. Parents seeded in Phase 1 start producing alerts and account rows. Scoring (pure math) can be developed in parallel within this phase.

---

## Behavioral specification

### Account types (detection timing)

| Path | Typical first on-chain signal |
|------|------------------------------|
| **Deposit wallet** | `WalletDeployed` and/or first fund — best for zero-trade watch |
| **Gnosis Safe** | Safe deployment on-chain |
| **Website / proxy** | Often first fund or first trade only |

**Factory addresses (Polygon mainnet):**

| Factory | Address |
|---------|---------|
| Deposit wallet | `0x00000000000Fb5C9ADea0298D729A0CB3823Cc07` |
| Proxy | `0xaB45c5A4B0c941a2F231C04C3f49182e1A254052` |
| Gnosis Safe | `0xaacfeea03eb1561c4e67d661e40682bd20e3541b` |

### Cluster score — scope (critical)

**Used only for:** discovery pipeline, alert queue ranking, sibling priority boost, analytics snapshots.

**NOT used for:** trade entry, exit rules, TP/SL, mirror size.

### Score formula (variant B default)

Implement A (log), B (sqrt), C (piecewise) in validation script. **Runtime default: sqrt.**

```python
# B) Square root — DEFAULT
profitScore = sqrt(max(profit, 0)) * W_PROFIT

efficiencyScore = min(profit / totalDeposited, EFFICIENCY_CAP) * W_EFFICIENCY  # if deposited > 0
winRateScore = max(0, winRate - 0.5) * W_WINRATE  # if exitCount >= minExitCount

accountWeight = profitScore + efficiencyScore + winRateScore  # if profit > 0; else 0
clusterScore = sum(accountWeight for all siblings)
```

**Default weights:** `W_PROFIT=2`, `W_EFFICIENCY=15`, `W_WINRATE=5`, `EFFICIENCY_CAP=10`

**Vetting:** Only accounts with positive realized profit contribute (losers = 0). Optional `subtractLossesFromClusterScore` for experiments.

**Recalc:** After any sibling position close; update alert ranks for open watch items.

### Protocol 1 — New account from flagged parent

| Event | Action |
|-------|--------|
| **FUND** | Log alert, attach to cluster, add to watchlist, start scanners |
| **BIRTH** | Watchlist + log only; scanners until FUND or first trade |
| **SIBLING** | Recalculate cluster score; apply priority multiplier |

**On FUND (automated):**

1. Log alert — parent, account, amount, timestamp, cluster score, sibling count
2. Link account to parent graph
3. Add to cluster watchlist — **no trade on fund alone**
4. Start scanners (§5.1)

### Scanners (cluster watch)

| Scanner | Action |
|---------|--------|
| **Trades** | Recalc net → entry or `net_adjustment` (Phase 3a+) |
| **Position balance** | Reconciliation if events missed (Phase 4) |
| **Resolution + redeem** | Close mirrored position if net flat |
| **Sibling overlap** | `CONFLICT` / `CONFLICT_RESOLVED` alerts |
| **Merge / split** | Log only in v0.1 |

### Alert ranking

1. `clusterScore` (desc)
2. Event type: FUND > BIRTH
3. Deposit size (desc)
4. `alert_time` ASC

---

## Implementation

### Ingestion layer

| Module | Purpose |
|--------|---------|
| `ingestion/base.py` | `IngestionAdapter` ABC + `RawEvent` model |
| `ingestion/polling/rpc_client.py` | Polygon RPC wrapper; log all calls to `rpc_logs` |
| `ingestion/polling/data_api.py` | Polymarket Data API + Gamma client |
| `ingestion/polling/event_detector.py` | FUND/BIRTH/trade detection from chain data |
| `ingestion/polling/adapter.py` | `PollingIngestionAdapter` |

**RawEvent shape:**

```python
class RawEvent(BaseModel):
    event_type: Literal["fund", "birth", "trade", "redeem", "merge_split"]
    parent_id: UUID
    account_id: UUID
    market_id: str | None = None
    tx_hash: str
    block_number: int
    timestamp: datetime
    amounts: dict[str, Any]
```

### Scoring layer (parallel track)

| Module | Purpose |
|--------|---------|
| `clustering/tracer.py` | Parent → account funding trace |
| `clustering/scorer.py` | Profit variants A/B/C, efficiency, winrate |
| `clustering/discovery.py` | Score recalc + alert rank update (no auto-flag yet) |

### Scheduler

| Module | Purpose |
|--------|---------|
| `scheduler/manager.py` | Asyncio periodic tasks |
| `scheduler/tasks.py` | `parent_watcher` (300s default), score recalc on demand |

Update `main.py` lifespan to start scheduler.

### Data flow — FUND event

```
parent_watcher → poll_batch() → detect_fund_events()
  → Account row (watch_status=active)
  → Alert (type=fund)
  → recalculate_cluster_score()
  → update_alert_ranks()
```

---

## Config changes

| Key | Default | Purpose |
|-----|---------|---------|
| `rpc_url` | `None` | Polygon RPC (env: `POLY_RPC_URL`) |
| `data_api_url` | `https://data-api.polymarket.com` | Data API base |
| `parent_watch_interval_sec` | `300` | FUND/BIRTH poll interval |

---

## DB changes

None. Writes to: `accounts`, `alerts`, `clusters`, `rpc_logs`.

---

## Test plan

| File | Coverage |
|------|----------|
| `tests/unit/test_scorer.py` | All 3 profit variants, efficiency cap, winrate gate |
| `tests/unit/test_event_detector.py` | FUND, BIRTH, account type classification |
| `tests/integration/test_ingestion_polling.py` | Adapter with mock RPC |
| `tests/integration/test_parent_watcher.py` | Seeded parent → FUND → DB rows + score |

Fixtures: `sample_events.json`, `labeled_wallets.json`

---

## Acceptance criteria

- [ ] `IngestionAdapter` + `RawEvent` defined
- [ ] FUND/BIRTH on seeded parents create `accounts` + `alerts`
- [ ] Cluster score recalculated after new sibling
- [ ] All 3 profit variants correct on `labeled_wallets.json`
- [ ] `rpc_logs` populated for every RPC call
- [ ] Scheduler runs `parent_watcher` on interval
- [ ] Alerts sorted by `cluster_score` desc
- [ ] All tests pass; lint clean

---

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | RPC provider | Alchemy vs QuickNode vs public Polygon |
| 2 | Multicall library | Multicall3 on Polygon — Phase 4 expands usage |
| 3 | Profit data source | Cashflow reconstruction vs Data API (spec prefers reconstruction) |
| 4 | Scheduler | Asyncio loops (recommended) vs APScheduler |
