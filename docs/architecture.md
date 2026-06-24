# PolyCrawler — Technical Architecture v0.1

> Living architecture document. Maps the spec (v0.1.5) to concrete modules, interfaces, data model, and build order.

---

## Design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Ingestion | **Polling-first via abstract adapter** | WebSocket swap-in later without touching engine |
| Foundation | **Build from scratch in Python** | Full control, no inherited debt |
| Async | **SQLAlchemy async + asyncpg + asyncio** | End-to-end async, aligns with FastAPI |
| Adapters | **IngestionAdapter + ExecutionAdapter** | Drop-in replacement for WS ingestion and live execution |

---

## 1. Project structure

```
poly-crawler/
├── pyproject.toml                        # Dependencies, metadata
├── Makefile                              # Common commands
├── alembic.ini                           # Migration config
├── alembic/
│   └── versions/                         # Auto-generated migrations
├── config/
│   ├── default.yaml                      # Baseline config (spec §14)
│   └── production.yaml                   # Prod overrides
├── src/
│   └── poly_crawler/
│       ├── __init__.py
│       ├── main.py                       # App lifecycle, startup/shutdown
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py                 # YAML + env → Pydantic
│       │   └── schema.py                 # Config models (spec §14)
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py                 # Async engine, session factory
│       │   └── models/                   # SQLAlchemy ORM models
│       │       ├── __init__.py
│       │       ├── parent.py
│       │       ├── account.py
│       │       ├── cluster.py
│       │       ├── cluster_position.py
│       │       ├── alert.py
│       │       ├── paper_trade.py
│       │       ├── session.py
│       │       ├── balance_snapshot.py
│       │       ├── rpc_log.py
│       │       ├── backtest_run.py
│       │       └── config_snapshot.py
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── base.py                   # Abstract IngestionAdapter
│       │   └── polling/                  # Default polling implementation
│       │       ├── __init__.py
│       │       ├── adapter.py            # PollingIngestionAdapter
│       │       ├── rpc_client.py         # web3.py Polygon calls
│       │       ├── data_api.py           # Polymarket Data API client
│       │       └── event_detector.py     # FUND/BIRTH/TRADE detection
│       ├── clustering/
│       │   ├── __init__.py
│       │   ├── tracer.py                 # Parent → account tracing
│       │   ├── scorer.py                 # Score variants A/B/C
│       │   └── discovery.py              # Auto-discovery, parent flagging
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── processor.py              # Main poll cycle (§6.4)
│       │   ├── state_machine.py          # Cluster×market FSM
│       │   ├── net_calculator.py         # Net exposure, deltas, mirror targets
│       │   ├── entry_rules.py            # §7.1 entry conditions
│       │   ├── exit_rules.py             # §8 exit conditions
│       │   ├── hedge_filter.py           # §7.5 hedge modes
│       │   └── reentry.py                # §7.6 follow re-entry
│       ├── execution/
│       │   ├── __init__.py
│       │   ├── base.py                   # Abstract ExecutionAdapter
│       │   └── paper/                    # Default paper implementation
│       │       ├── __init__.py
│       │       ├── adapter.py            # PaperExecutionAdapter
│       │       └── orderbook_walk.py     # §10.1 fill model
│       ├── analytics/
│       │   ├── __init__.py
│       │   ├── session_manager.py        # Session lifecycle
│       │   ├── event_logger.py           # Structured event persistence
│       │   └── aggregator.py             # Global rollups
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                    # FastAPI app factory
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── alerts.py
│       │       ├── positions.py
│       │       ├── sessions.py
│       │       └── config.py
│       └── scheduler/
│           ├── __init__.py
│           ├── manager.py                # asyncio task orchestration
│           └── tasks.py                  # Periodic job definitions
├── tests/
│   ├── conftest.py                       # Fixtures, test DB, mocks
│   ├── unit/
│   │   ├── test_scorer.py
│   │   ├── test_state_machine.py
│   │   ├── test_entry_rules.py
│   │   ├── test_exit_rules.py
│   │   ├── test_net_calculator.py
│   │   ├── test_hedge_filter.py
│   │   └── test_reentry.py
│   ├── integration/
│   │   ├── test_ingestion_polling.py
│   │   ├── test_engine_cycle.py
│   │   └── test_paper_execution.py
│   └── fixtures/
│       ├── labeled_wallets.json
│       ├── sample_events.json
│       └── sample_orderbook.json
└── docs/
    └── architecture.md                   # This document
```

---

## 2. Database schema

### 2.1 Entity relationships

```
parents ──1:1── clusters
parents ──1:N── accounts
clusters ──1:N── cluster_positions
clusters ──1:N── alerts
accounts ──1:N── sibling_balance_snapshots
cluster_positions ──1:N── paper_trades
sessions ──1:N── paper_trades
sessions ──1:N── backtest_runs
```

### 2.2 Table definitions

#### `parents`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK, default gen_random_uuid() | |
| chain_address | VARCHAR(42) | NOT NULL, UNIQUE | 0x-prefixed |
| first_seen_at | TIMESTAMPTZ | NOT NULL, default now() | |
| last_seen_at | TIMESTAMPTZ | NOT NULL, default now() | |
| is_ignored | BOOLEAN | NOT NULL, default FALSE | Exclude from watch/ranking |
| metadata | JSONB | default '{}' | Flexible enrichment |
| created_at | TIMESTAMPTZ | NOT NULL, default now() | |

Indexes: `(is_ignored) WHERE is_ignored = FALSE`, `(chain_address)`

#### `accounts`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| polymarket_address | VARCHAR(42) | NOT NULL, UNIQUE | |
| account_type | VARCHAR(20) | NOT NULL, CHECK IN | deposit_wallet, safe, proxy, unknown |
| parent_id | UUID | NOT NULL, FK → parents.id | CASCADE delete |
| watch_status | VARCHAR(20) | NOT NULL, DEFAULT 'active' | active, expired |
| first_funded_at | TIMESTAMPTZ | nullable | |
| last_activity_at | TIMESTAMPTZ | nullable | |
| metadata | JSONB | default '{}' | |
| created_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `(parent_id)`, `(watch_status) WHERE watch_status = 'active'`

#### `clusters`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| parent_id | UUID | NOT NULL, UNIQUE, FK → parents.id | One cluster per parent |
| cluster_score | DOUBLE PRECISION | DEFAULT 0 | |
| score_variant | VARCHAR(10) | DEFAULT 'sqrt' | sqrt, log, piecewise |
| last_scored_at | TIMESTAMPTZ | nullable | |
| sibling_count | INTEGER | DEFAULT 0 | |
| vetted_sibling_count | INTEGER | DEFAULT 0 | Only profitable ones |
| created_at | TIMESTAMPTZ | NOT NULL | |

#### `cluster_positions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| cluster_id | UUID | NOT NULL, FK → clusters.id | |
| market_id | VARCHAR(64) | NOT NULL | CLOB market ID |
| market_slug | VARCHAR(255) | nullable | |
| market_title | TEXT | nullable | |
| market_tags | JSONB | default '[]' | |
| state | VARCHAR(20) | NOT NULL, DEFAULT 'watching', CHECK IN | watching, signal, in_position, closed, skipped |
| net_exposure | BIGINT | DEFAULT 0 | Signed: Yes - No |
| last_known_net | BIGINT | DEFAULT 0 | For delta calculation |
| mirrored_yes | BIGINT | DEFAULT 0 | Our current Yes shares |
| mirrored_no | BIGINT | DEFAULT 0 | Our current No shares |
| sibling_balances | JSONB | default '{}' | {accountId: {yes, no}} |
| tp_sl_suspended | BOOLEAN | NOT NULL, DEFAULT FALSE | Until net ~0 |
| last_closed_at | TIMESTAMPTZ | nullable | |
| last_closed_reason | VARCHAR(40) | nullable | cluster_hedged, tp_hit, sl_hit, resolved, reconciled |
| config_snapshot_id | UUID | FK → config_snapshots.id | Entry config at time of entry |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `(state)`, `(cluster_id)`, UNIQUE `(cluster_id, market_id)`

#### `alerts`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| parent_id | UUID | FK → parents.id | nullable |
| account_id | UUID | FK → accounts.id | nullable |
| cluster_id | UUID | FK → clusters.id | nullable |
| alert_type | VARCHAR(30) | NOT NULL, CHECK IN | fund, birth, sibling, conflict, conflict_resolved, signal, entry, exit |
| amount_usd | DOUBLE PRECISION | nullable | |
| cluster_score_at_event | DOUBLE PRECISION | nullable | |
| rank | INTEGER | nullable | Sort position |
| metadata | JSONB | default '{}' | Net, balances snapshot, etc. |
| is_false_positive | BOOLEAN | DEFAULT NULL | null = unlabeled |
| created_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `(parent_id)`, `(cluster_id)`, `(alert_type)`, `(is_false_positive) WHERE is_false_positive IS NULL`

#### `paper_trades`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| cluster_position_id | UUID | FK → cluster_positions.id | |
| session_id | UUID | FK → sessions.id | |
| event_type | VARCHAR(20) | NOT NULL, CHECK IN | entry, net_adjustment, exit |
| sibling_account_id | UUID | FK → accounts.id | Source sibling |
| net_before | BIGINT | nullable | |
| net_after | BIGINT | nullable | |
| net_delta | BIGINT | nullable | |
| our_side | VARCHAR(4) | CHECK IN | yes, no |
| our_shares | BIGINT | nullable | |
| our_fill_price | DOUBLE PRECISION | nullable | Volume-weighted avg |
| our_fill_usd | DOUBLE PRECISION | nullable | |
| source_tx | VARCHAR(66) | nullable | Triggering tx hash |
| reason | VARCHAR(40) | nullable | |
| latency_ms | INTEGER | nullable | Signal → fill |
| book_snapshot_id | VARCHAR(64) | nullable | CLOB snapshot ref |
| slippage_bps | INTEGER | nullable | |
| created_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `(cluster_position_id)`, `(session_id)`

#### `sibling_balance_snapshots`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| account_id | UUID | NOT NULL, FK → accounts.id | |
| cluster_id | UUID | NOT NULL, FK → clusters.id | |
| market_id | VARCHAR(64) | NOT NULL | |
| yes_shares | BIGINT | DEFAULT 0 | |
| no_shares | BIGINT | DEFAULT 0 | |
| polled_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `(account_id)`, `(cluster_id, market_id)`

#### `sessions`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| name | VARCHAR(255) | nullable | |
| mode | VARCHAR(10) | NOT NULL, CHECK IN | observe, paper, live |
| review_mode | VARCHAR(10) | NOT NULL, CHECK IN | all, live_only, none |
| config_snapshot | JSONB | NOT NULL | Immutable config copy |
| private | BOOLEAN | NOT NULL, DEFAULT FALSE | Exclude from global analytics |
| started_at | TIMESTAMPTZ | NOT NULL | |
| ended_at | TIMESTAMPTZ | nullable | |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'running' | running, completed, aborted |

#### `config_snapshots`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| config_json | JSONB | NOT NULL | |
| created_at | TIMESTAMPTZ | NOT NULL | |

#### `rpc_logs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| method | VARCHAR(100) | NOT NULL | |
| params | TEXT | nullable | |
| provider | VARCHAR(50) | nullable | Alchemy, QuickNode, etc. |
| latency_ms | INTEGER | nullable | |
| error | TEXT | nullable | |
| created_at | TIMESTAMPTZ | NOT NULL | |

#### `backtest_runs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| session_id | UUID | FK → sessions.id | |
| config_snapshot | JSONB | nullable | |
| score_variant | VARCHAR(10) | nullable | sqrt, log, piecewise |
| started_at | TIMESTAMPTZ | NOT NULL | |
| completed_at | TIMESTAMPTZ | nullable | |
| status | VARCHAR(20) | DEFAULT 'running' | running, completed, failed |

---

## 3. Configuration system

### 3.1 Load chain

```
default.yaml (committed) ──► env vars (POLY_*) ──► user override YAML ──► session override (DB)
       │                        │                      │                       │
       ▼                        ▼                      ▼                       ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │                         Pydantic BaseSettings                            │
   │   Models mirror spec §14 exactly. Env pattern: POLY_ENTRY_MIN_BUY_USD    │
   └──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Top-level config structure

```yaml
discovery:
  min_sibling_count: 2
  min_cluster_score: null
  funding_hops: 3
  profit_formula: sqrt
  subtract_losses: false
  weights:
    profit: 2.0
    efficiency: 15.0
    win_rate: 5.0
  efficiency_cap: 10.0
  min_exit_count_for_win_rate: 1

entry:
  min_buy_usd: 500.0
  market_tags: []
  max_odds_enabled: true
  max_odds: 0.5
  mirror_pct: 1.0
  mirror_cap_usd: null
  post_entry_poll_interval_sec: 10
  post_entry_poll_count: 6
  hedge_filter_mode: net_only
  ignore_hedge_trades: true
  hedge_dominant_threshold: 2.0
  follow_reentry_after_sell: true
  reentry_window_minutes: 5

exit:
  poll_interval_sec: 60
  take_profit_enabled: false
  take_profit_pct: 0.50
  stop_loss_enabled: false
  stop_loss_pct: 0.25
  max_hold_hours: null
  close_on_resolution: true

review:
  mode: live_only

paper:
  fill_model: orderbook_walk_next_poll
  pessimistic_slippage_pct: 0.0

conflict:
  policy: net_cluster_position
  min_net_usd: 100.0
  dust_shares: 0.001
  always_alert: true
```

---

## 4. Component interfaces

### 4.1 IngestionAdapter (abstract)

```python
class RawEvent(BaseModel):
    event_type: Literal['fund', 'birth', 'trade', 'redeem', 'merge_split']
    parent_id: UUID
    account_id: UUID
    market_id: str | None = None
    tx_hash: str
    block_number: int
    timestamp: datetime
    amounts: dict

class IngestionAdapter(ABC):
    """Swap polling ↔ WebSocket without touching the engine."""
    
    @abstractmethod
    async def poll_batch(self) -> list[RawEvent]:
        """All new events since last poll."""
    
    @abstractmethod
    async def fetch_balances(self, account_ids: list[UUID]) -> dict[UUID, dict[str, dict[str, int]]]:
        """Current Yes/No balances per market per account."""
    
    @abstractmethod
    async def fetch_orderbook(self, market_id: str, side: str) -> list[dict]:
        """CLOB order book for paper fill pricing."""
```

### 4.2 ExecutionAdapter (abstract)

```python
class EntrySignal(BaseModel):
    cluster_position_id: UUID
    market_id: str
    side: Literal['yes', 'no']
    shares: int
    max_price: float | None = None

class FillResult(BaseModel):
    success: bool
    filled_shares: int
    avg_price: float
    slippage_bps: int
    book_snapshot: dict | None = None

class ExecutionAdapter(ABC):
    """Swap paper ↔ live without touching the engine."""
    
    @abstractmethod
    async def execute_entry(self, signal: EntrySignal) -> FillResult: ...
    
    @abstractmethod
    async def execute_exit(self, signal: EntrySignal) -> FillResult: ...
```

### 4.3 Engine (central coordinator)

```python
class Engine:
    """Owns the poll cycle, routes events through the FSM."""
    
    def __init__(self, 
                 ingestion: IngestionAdapter, 
                 execution: ExecutionAdapter, 
                 config: Config, 
                 db: AsyncSession):
        ...
    
    async def run_poll_cycle(self):
        """One cycle: poll → event process → reconcile → execute."""
        events = await self.ingestion.poll_batch()
        for event in sorted(events, key=lambda e: e.timestamp):
            await self._process_event(event)
        await self._reconcile_positions()
    
    async def _process_event(self, event: RawEvent):
        """Identify affected cluster×market → update balances → FSM transition."""
        ...
```

---

## 5. State machine (Protocol 2)

### 5.1 States

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
                                                 (same poll tick)
```

### 5.2 Implementation approach

```python
class PositionState(str, Enum):
    WATCHING = 'watching'
    SIGNAL = 'signal'
    IN_POSITION = 'in_position'
    CLOSED = 'closed'
    SKIPPED = 'skipped'

class PositionFSM:
    def __init__(self, db_row: ClusterPosition, config: Config):
        self.state = db_row.state
        self.row = db_row
        self.config = config
    
    async def process(self, ctx: EngineContext) -> list[Action]:
        handler = {
            PositionState.WATCHING: self._handle_watching,
            PositionState.IN_POSITION: self._handle_in_position,
            PositionState.SIGNAL: self._handle_signal,
            PositionState.SKIPPED: self._handle_skipped,
            PositionState.CLOSED: self._handle_closed,
        }.get(self.state, self._fallback)
        return await handler(ctx)
```

Each handler returns a list of `Action` objects (enter, exit, adjust, alert). The action list is executed by the processor, then state is persisted.

---

## 6. Task scheduling

### 6.1 Task definitions

| Task | Interval | Purpose |
|------|----------|---------|
| `parent_watcher` | 300s (configurable) | FUND/BIRTH detection on seeded parents |
| `balance_poll` | `exit.poll_interval_sec` (60s) | Fetch balances, run engine cycle |
| `fast_post_entry` | 10s × 6 cycles | Triggered per position after entry |
| `reconciliation` | Every 3rd balance poll | Full balance rebuild from Data API |
| `rpc_log_cleanup` | Daily | Prune old logs |

### 6.2 Scheduler

```python
class TaskManager:
    tasks: dict[str, asyncio.Task]
    
    async def periodic(self, name: str, interval_sec: int, fn: Callable):
        """Run fn every interval_sec."""
    
    async def fast_poll_for(self, cluster_position_id: UUID):
        """Schedule 6× fast polls after entry, then return to normal."""
```

---

## 7. Data flows

### 7.1 New sibling trade → entry

```
1. Poll cycle starts
2. EventDetector: account 0x... bought +200 Yes in "will-x-win"
3. RawEvent created → engine.process_event()
4. Load cluster_position for (cluster, market) → WATCHING
5. NetCalculator: update sibling_balances, recalc net = +200
6. EntryRules.evaluate(net=+200, market_tags, odds, minBuyUsd)
   → passes → review required?
   - live_only + paper → auto IN_POSITION
   - review required → SIGNAL
7. ExecutionAdapter.execute_entry() → FillResult
8. PaperTrade persisted, cluster_position updated
9. Alert: type=entry
```

### 7.2 IN_POSITION — net delta

```
1. Poll: balances now 250 Yes (+50 delta)
2. NetCalculator: delta = +50
3. ExitRules: TP/SL/max-hold — none hit
4. EntryRules: skipped (already IN_POSITION)
5. Mirror delta: +50 × mirrorPct
6. PaperTrade: reason=net_adjustment
7. cluster_position.updated_at bumped
```

### 7.3 Exit — cluster net flat

```
1. Poll: sibling sold 200 Yes → net = +50 (below min_net_usd=100)
2. ExitRules: net ≈ 0 → cluster_hedged
3. ExecutionAdapter: close position (sell 200 Yes)
4. PaperTrade: exit, reason=cluster_hedged
5. cluster_position → CLOSED → immediately → WATCHING
6. last_closed_at set. tp_sl_suspended NOT set (reason ≠ tp/sl)
7. Alert: type=exit
```

---

## 8. Paper fill model (§10.1)

```python
async def walk_orderbook(api: DataAPI, market_id: str, side: str, target_shares: int) -> FillResult:
    """CLOB orderbook walk. Returns volume-weighted avg price and slippage."""
    book = await api.get_orderbook(market_id, side)
    remaining = target_shares
    total_cost = 0.0
    levels = []
    
    for level in sorted(book['levels'], key=lambda l: l['price']):
        fill = min(remaining, level['shares'])
        total_cost += fill * level['price']
        remaining -= fill
        levels.append(level)
        if remaining <= 0:
            break
    
    avg_price = total_cost / target_shares
    mid = (book['bid'] + book['ask']) / 2
    slippage = int(abs(avg_price - mid) / mid * 10000)
    
    return FillResult(
        success=remaining == 0,
        filled_shares=target_shares - remaining,
        avg_price=avg_price,
        slippage_bps=slippage,
        book_snapshot={'levels': levels},
    )
```

---

## 9. Scoring module (§4)

```python
# Variants
def profit_log(profit: float, w: float) -> float:
    return log10(1 + max(profit, 0)) * w

def profit_sqrt(profit: float, w: float) -> float:
    return sqrt(max(profit, 0)) * w                     # DEFAULT

def profit_piecewise(profit: float, w: float) -> float:
    if profit <= 10000:
        return (profit / 1000) * (w / 10)
    return 10 * (w / 10) + log10(profit / 10000) * 5

# Components
def efficiency(profit: float, deposited: float, cap: float, w: float) -> float:
    if deposited <= 0:
        return 0.0
    return min(profit / deposited, cap) * w

def winrate(win_rate: float, exits: int, min_exits: int) -> float:
    if exits < min_exits:
        return 0.0
    return max(0.0, win_rate - 0.5) * W_WINRATE

# Aggregation
def account_weight(profit, variant, weights, ...) -> float: ...
def cluster_score(siblings: list, config: Config) -> float: ...
```

A validation script (`scripts/validate_scores.py`) computes all three variants on ~20 labeled wallets (10 suspicious, 10 normal) to tune `minClusterScore` before enabling auto-discovery.

---

## 10. API layer

### 10.1 Routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | /alerts | List alerts (filter: type, parent, time range) |
| PATCH | /alerts/{id} | Set is_false_positive |
| GET | /positions | List cluster positions (filter: state, cluster) |
| GET | /positions/{id} | Position detail + trade history |
| GET | /sessions | List sessions |
| POST | /sessions | Create session |
| PATCH | /sessions/{id} | Update session (end, private toggle) |
| GET | /config | Current runtime config |
| PUT | /config | Update config (live reload) |
| GET | /stats/global | Global analytics rollup |

### 10.2 Stack

```python
# api/app.py
from fastapi import FastAPI

def create_app(engine: Engine, config: Config) -> FastAPI:
    app = FastAPI(title='PolyCrawler', version='0.1.0')
    # Register route groups
    app.include_router(alerts.router, prefix='/alerts', tags=['alerts'])
    app.include_router(positions.router, prefix='/positions', tags=['positions'])
    app.include_router(sessions.router, prefix='/sessions', tags=['sessions'])
    app.include_router(config_router, prefix='/config', tags=['config'])
    return app
```

Frontend: TBD (API-first in v0.1, frontend in a later design pass).

---

## 11. Testing strategy

### 11.1 Unit tests (fast, mocked, no DB)

| File | Coverage |
|------|----------|
| `test_scorer.py` | All 3 profit variants, efficiency cap, winrate min-exits, cluster_score aggregation |
| `test_state_machine.py` | Every FSM transition (W→S, W→P, P→C, C→W, etc.) |
| `test_entry_rules.py` | min_buy_usd gate, max_odds, market_tags allowlist, condition combinations |
| `test_exit_rules.py` | TP, SL, max_hold, cluster_hedged, resolution, priority ordering |
| `test_net_calculator.py` | Net calc, deltas, mirror targets, cap enforcement |
| `test_hedge_filter.py` | net_only vs filter_before_net on same-fill hedges |
| `test_reentry.py` | Re-entry window timing, flat→non-zero logic |

### 11.2 Integration tests (DB + async)

| File | Coverage |
|------|----------|
| `test_ingestion_polling.py` | Polling adapter with mock RPC/API → RawEvent creation |
| `test_engine_cycle.py` | Full cycle: events → FSM → trades, DB persistence |
| `test_paper_execution.py` | Orderbook walk with mock CLOB data, fill accuracy |

### 11.3 Test fixtures

- `labeled_wallets.json`: ~20 wallets with known profit/efficiency/winrate
- `sample_events.json`: Pre-built FUND/BIRTH/TRADE events
- `sample_orderbook.json`: CLOB order books at various depths

---

## 12. Build order

| Order | Phase (spec §16) | Deliverable | Key modules |
|-------|-------------------|-------------|-------------|
| 0 | **Bootstrap** | pyproject.toml, package skeleton, config loading, alembic setup, test harness | config/, db/, tests/conftest.py |
| 1 | **Manual seed** (§16.1) | parents, accounts, clusters tables & migration. CLI to seed parent wallets | db/models/, alembic/ |
| 2 | **Parent watcher** (§16.2) | IngestionAdapter, polling impl, FUND/BIRTH detection, alert creation, scheduler task | ingestion/, scheduler/ |
| 3 | **Paper engine** (§16.3) | All remaining tables. State machine, net calc, entry/exit rules, hedge filter, re-entry, paper execution, orderbook walk, full poll cycle | engine/, execution/paper/, analytics/ |
| 4 | **Reconciliation** (§16.4) | Balance multicall, reconciliation scanner, rpc_logs | engine/ (reconciliation), ingestion/ |
| 5 | **Dashboard** (§16.5) | FastAPI app, alert/position/session/config routes | api/ |
| 6 | **Backtesting** (§16.6) | Backtest framework, score validation script, historical replay | scripts/, backtest models |
| 7 | **Auto-discovery** (§16.7) | Discovery pipeline, auto-flagging with minClusterScore | clustering/ |
| 8 | **Live** (§16.8) | Live execution adapter, real CLOB submission | execution/live/ |

---

## 13. Architectural invariants

1. **Ingestion never touches engine state.** `IngestionAdapter` produces `RawEvent` objects; engine consumes them.
2. **Execution never touches engine state.** `ExecutionAdapter` receives signals, returns fill results.
3. **Config is immutable per session.** Each session captures a `config_snapshot` for deterministic replay.
4. **Net is authoritative.** Reconciliation (polled balances) always overwrites event-derived balances.
5. **State machine is the SSoT.** `cluster_positions.state` drives all behavior. No derived state elsewhere.
6. **All external calls go through adapters.** RPC, Data API, CLOB — all behind interfaces for testability.
