# Phase 2 — Parent Watcher + Scoring

**Source:** spec.md §16.2, §4, §5 | docs/architecture.md §4.1, §6, §9
**Status:** ⬜ Not started
**Prerequisites:** [Phase 1](phase1-manual-seed.md) complete

---

## Goal

Build the ingestion layer: poll Polygon for FUND/BIRTH events on seeded parents, detect new sibling accounts, and compute cluster scores. This phase makes the system "see" the blockchain — parents seeded in Phase 1 start producing alerts and account rows. The scoring module (pure math) can be developed in parallel within this phase.

## Spec references

- spec §5 — Protocol 1: New account from flagged parent (FUND/BIRTH/SIBLING events)
- spec §4 — Cluster score: per-account weight, profit variants, discovery flagging
- spec §3 — Account types and factory addresses
- spec §5.1 — Scanners (cluster watch)
- arch §4.1 — IngestionAdapter abstract interface
- arch §6 — Task scheduling (parent_watcher interval)
- arch §9 — Scoring module (profit variants, efficiency, winrate)

## Prerequisites

- Phase 1 complete (parents seeded in DB, CLI working)
- A Polygon RPC provider URL configured (Alchemy/QuickNode — open question #3 needs resolution)
- `web3.py` installed (already in deps)

## Modules to build

### Ingestion layer

#### 1. `src/poly_crawler/ingestion/base.py` — Abstract adapter + RawEvent

The contract every ingestion implementation must satisfy. Already specified in [component-interfaces.md](../architecture/component-interfaces.md).

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

class IngestionAdapter(ABC):
    @abstractmethod
    async def poll_batch(self) -> list[RawEvent]:
        """All new events since last poll."""

    @abstractmethod
    async def fetch_balances(
        self, account_ids: list[UUID]
    ) -> dict[UUID, dict[str, dict[str, int]]]:
        """Current Yes/No balances per market per account."""

    @abstractmethod
    async def fetch_orderbook(self, market_id: str, side: str) -> list[dict]:
        """CLOB order book for paper fill pricing."""
```

#### 2. `src/poly_crawler/ingestion/polling/rpc_client.py` — Polygon RPC wrapper

Wraps `web3.py` for Polygon chain calls. All RPC interactions go through here so we can log to `rpc_logs`.

**Functions:**

| Function | Purpose |
|----------|---------|
| `RpcClient.__init__(rpc_url, provider_name)` | Initialize web3 instance |
| `async get_block_transactions(block_number) -> list[dict]` | Fetch txs from a block |
| `async get_latest_block_number() -> int` | Current chain head |
| `async get_transaction_receipt(tx_hash) -> dict` | Tx receipt for event parsing |
| `async multicall_balance_check(addresses) -> dict` | Batch ERC-20 balance checks |
| `async get_transaction_events(tx_hash, event_sig) -> list[dict]` | Decode log events |

**Logging:** Every RPC call writes a row to `rpc_logs` (method, params, provider, latency_ms, error). Use a decorator or wrapper to automate this.

#### 3. `src/poly_crawler/ingestion/polling/data_api.py` — Polymarket Data API client

HTTP client for Polymarket's Data API and Gamma API. Uses `httpx`.

**Functions:**

| Function | Purpose |
|----------|---------|
| `DataApiClient.__init__(base_url)` | httpx async client |
| `async get_account_positions(address) -> list[dict]` | Fetch YES/NO balances per market |
| `async get_market_info(market_id) -> dict` | Market metadata (slug, title, tags, resolution status) |
| `async get_orderbook(market_id, side) -> dict` | CLOB order book levels (used in Phase 3b) |
| `async is_market_resolved(market_id) -> bool` | Resolution check (used in Phase 3a exit rules) |

#### 4. `src/poly_crawler/ingestion/polling/event_detector.py` — Event detection

Parses chain data into `RawEvent` objects. This is the translation layer between "raw blockchain data" and "domain events the engine understands."

**Functions:**

| Function | Purpose |
|----------|---------|
| `detect_fund_events(tx, parent_addresses) -> list[RawEvent]` | USDC transfers to Polymarket proxy contracts |
| `detect_birth_events(tx, factory_addresses) -> list[RawEvent]` | WalletDeployed / Safe creation events |
| `detect_trade_events(tx) -> list[RawEvent]` | CLOB order fills (buy/sell YES/NO) |
| `classify_account_type(tx) -> str` | deposit_wallet / safe / proxy / unknown |

**Factory addresses (spec §3):**

| Factory | Address |
|---------|---------|
| Deposit wallet | `0x00000000000Fb5C9ADea0298D729A0CB3823Cc07` |
| Proxy | `0xaB45c5A4B0c941a2F231C04C3f49182e1A254052` |
| Gnosis Safe | `0xaacfeeaea03eb1561c4e67d661e40682bd20e3541b` |

#### 5. `src/poly_crawler/ingestion/polling/adapter.py` — PollingIngestionAdapter

Concrete implementation of `IngestionAdapter` using polling. This is the default adapter — a WebSocket adapter can replace it later without touching the engine.

```python
class PollingIngestionAdapter(IngestionAdapter):
    def __init__(self, rpc: RpcClient, data_api: DataApiClient, config: Config):
        self._rpc = rpc
        self._data_api = data_api
        self._config = config
        self._last_block = 0

    async def poll_batch(self) -> list[RawEvent]:
        current = await self._rpc.get_latest_block_number()
        events = []
        for block in range(self._last_block + 1, current + 1):
            txs = await self._rpc.get_block_transactions(block)
            for tx in txs:
                events.extend(await self._detect_events(tx))
        self._last_block = current
        return events
```

### Scoring layer (parallel track within this phase)

#### 6. `src/poly_crawler/clustering/tracer.py` — Parent → account tracing

Traces funding hops from a parent wallet to find linked Polymarket accounts.

**Functions:**

| Function | Purpose |
|----------|---------|
| `trace_funding(parent_address, max_hops) -> list[str]` | Follow USDC transfers up to `funding_hops` deep |
| `find_polymarket_accounts(address) -> list[Account]` | Check if an address is a Polymarket account (proxy/Safe/deposit) |

#### 7. `src/poly_crawler/clustering/scorer.py` — Score variants A/B/C

Pure math module. All three profit variants implemented here for validation. **B (sqrt) is the runtime default.**

**Functions (from arch §9):**

```python
def profit_log(profit: float, w: float) -> float:
    return log10(1 + max(profit, 0)) * w

def profit_sqrt(profit: float, w: float) -> float:  # DEFAULT
    return sqrt(max(profit, 0)) * w

def profit_piecewise(profit: float, w: float) -> float:
    if profit <= 10000:
        return (profit / 1000) * (w / 10)
    return 10 * (w / 10) + log10(profit / 10000) * 5

def efficiency(profit: float, deposited: float, cap: float, w: float) -> float:
    if deposited <= 0:
        return 0.0
    return min(profit / deposited, cap) * w

def winrate(win_rate: float, exits: int, min_exits: int, w: float) -> float:
    if exits < min_exits:
        return 0.0
    return max(0.0, win_rate - 0.5) * w

def account_weight(profit, variant, weights, ...) -> float: ...
def cluster_score(siblings: list, config: Config) -> float: ...
```

**Default weights:** `W_PROFIT=2.0`, `W_EFFICIENCY=15.0`, `W_WINRATE=5.0`, `EFFICIENCY_CAP=10`

#### 8. `src/poly_crawler/clustering/discovery.py` — Parent flagging (basic)

In Phase 2, discovery is manual-seed-only. This module handles the **recalculation** of cluster scores after new siblings are found, but does NOT auto-flag parents (that's Phase 7).

**Functions:**

| Function | Purpose |
|----------|---------|
| `recalculate_cluster_score(session, cluster_id) -> float` | Re-score a cluster after sibling changes |
| `update_alert_ranks(session) -> None` | Re-sort open alerts by cluster_score desc |

### Scheduler layer

#### 9. `src/poly_crawler/scheduler/manager.py` — Task orchestration

Asyncio-based task manager that runs periodic jobs. Not APScheduler yet — pure asyncio tasks with sleep loops (simpler, fewer deps, sufficient for v0.1).

```python
class TaskManager:
    tasks: dict[str, asyncio.Task]

    async def periodic(self, name: str, interval_sec: int, fn: Callable):
        """Run fn every interval_sec until cancelled."""

    async def fast_poll_for(self, cluster_position_id: UUID):
        """Schedule 6× fast polls after entry (used in Phase 3b)."""

    async def start_all(self):
        """Start all registered periodic tasks."""

    async def stop_all(self):
        """Cancel all running tasks."""
```

#### 10. `src/poly_crawler/scheduler/tasks.py` — Periodic job definitions

| Task | Interval | Purpose |
|------|----------|---------|
| `parent_watcher` | 300s (configurable) | Poll for FUND/BIRTH on seeded parents |
| `score_recalculator` | On-demand | Recalculate cluster score after sibling discovery |

### Integration with main.py

Update `main.py` lifespan to start the scheduler:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config = load_config()
    init_engine(config)
    # Phase 2: start scheduler
    task_manager = TaskManager()
    await task_manager.start_all()
    yield
    await task_manager.stop_all()
    await close_engine()
```

## Data flow

### FUND event detection

```
1. parent_watcher task fires (every 300s)
2. PollingIngestionAdapter.poll_batch()
   → RpcClient scans new blocks for USDC transfers FROM parent addresses
3. EventDetector.detect_fund_events(tx, parent_addresses)
   → If USDC transfer from a seeded parent to a Polymarket proxy/Safe
   → Creates RawEvent(event_type="fund", parent_id, account_id, amounts)
4. Engine processes event (Phase 3 — not yet, just persist)
5. For now: create Account row (polymarket_address, parent_id, watch_status="active")
6. Create Alert (alert_type="fund", parent_id, account_id, amount_usd)
7. Recalculate cluster score (new sibling added)
8. Update alert ranks
```

### BIRTH event detection

```
1. parent_watcher scans for WalletDeployed / SafeCreation events
2. If the deploying address is a seeded parent → RawEvent(event_type="birth")
3. Create Account row (watch_status="active", account_type="deposit_wallet"/"safe")
4. Create Alert (alert_type="birth")
5. No scoring impact yet (no trades to score)
```

### Cluster score recalculation

```
1. New sibling discovered (FUND event)
2. tracer.find_polymarket_accounts(parent_address) → all linked accounts
3. For each account: fetch realized profit, deposited, exits, win_rate from Data API
4. scorer.account_weight(profit, variant, weights, ...) per sibling
5. scorer.cluster_score(siblings, config) → sum of weights
6. Update clusters.cluster_score, clusters.last_scored_at, clusters.sibling_count
7. discovery.update_alert_ranks(session) → re-sort open alerts
```

## Config changes

| New key | Type | Default | Purpose |
|---------|------|---------|---------|
| `rpc_url` | `str | None` | `None` | Polygon RPC provider URL (env: `POLY_RPC_URL`) |
| `data_api_url` | `str` | `"https://data-api.polymarket.com"` | Polymarket Data API base URL |
| `parent_watch_interval_sec` | `int` | `300` | How often to poll for new FUND/BIRTH events |

Add to `Config` in `schema.py` and `default.yaml`.

## DB changes

None. All tables exist. This phase writes to: `accounts`, `alerts`, `clusters` (score updates), `rpc_logs`.

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_scorer.py` | All 3 profit variants (log, sqrt, piecewise) with known inputs; efficiency cap; winrate min-exits gate; account_weight aggregation; cluster_score sum; subtract_losses behavior |
| `tests/unit/test_event_detector.py` | FUND detection from mock tx data; BIRTH detection; account type classification; factory address matching |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_ingestion_polling.py` | PollingIngestionAdapter with mock RpcClient → RawEvent creation; poll_batch returns events in timestamp order; last_block tracking |
| `tests/integration/test_parent_watcher.py` | Full cycle: seeded parent → mock FUND event → Account + Alert created in DB → cluster score recalculated |

### Fixtures used

| Fixture | Used by |
|---------|---------|
| `tests/fixtures/sample_events.json` | Event detector tests (fund, birth, trade events) |
| `tests/fixtures/labeled_wallets.json` | Scorer tests (parent with 3 siblings, known score 18.3) |

## Acceptance criteria

- [ ] `IngestionAdapter` ABC + `RawEvent` model defined in `ingestion/base.py`
- [ ] `PollingIngestionAdapter` implements all 3 abstract methods
- [ ] FUND events on seeded parents create `accounts` + `alerts` rows
- [ ] BIRTH events create `accounts` + `alerts` rows
- [ ] Cluster score recalculated after new sibling discovery
- [ ] All 3 profit variants produce correct outputs on `labeled_wallets.json` fixture
- [ ] `rpc_logs` populated for every RPC call
- [ ] Scheduler runs `parent_watcher` task on interval
- [ ] Alert ranks sorted by `cluster_score` desc
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | RPC provider (open question #3) | Must decide: Alchemy vs QuickNode vs free Polygon RPC. Affects rate limits and cost. |
| 2 | Multicall implementation | Use `web3.py` multicall library or roll our own batch? Multicall3 contract on Polygon. |
| 3 | Event detection granularity | Poll by block range or by transaction? Block range is simpler but may miss events in reorgs. |
| 4 | Should scorer fetch profit data from Data API or chain? | Data API has `cashPnl` but spec says use realized PnL via cashflow reconstruction. Need to decide reconstruction approach. |
| 5 | Scheduler: asyncio loops vs APScheduler | asyncio loops recommended for v0.1 (simpler, fewer deps). APScheduler already in deps but adds complexity. |
