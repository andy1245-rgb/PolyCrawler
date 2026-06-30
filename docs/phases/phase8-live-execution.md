# Phase 8 — Live Execution

**Source:** spec.md §16.8, §10 | docs/architecture.md §4.2, §12
**Status:** ⬜ Not started
**Prerequisites:** All previous phases complete (paper engine proven, dashboard operational, backtesting validated)

---

## Goal

Implement a live `ExecutionAdapter` that places real CLOB orders on Polymarket. The engine code doesn't change at all — this is the payoff of the adapter pattern. Flip `execution.mode: live` and real trades execute through the same FSM, entry/exit rules, and net mirroring logic that paper mode used.

## Spec references

- spec §10 — Execution modes (observe/paper/live, shared engine, swappable adapter)
- spec §16.8 — Live execution deliverable
- spec §8.4 — Slippage guard (live only, `exit.max_slippage_pct`)
- spec §15 — Tech stack (CLOB signing, exchange connectivity)
- arch §4.2 — ExecutionAdapter abstract interface
- arch §13 — Architectural invariant: "All external calls go through adapters"

## Prerequisites

- Phase 3b complete: paper engine proven with profitable backtests
- Phase 5 complete: dashboard operational (need to monitor live trades)
- Phase 6 complete: backtesting validates the strategy
- Paper PnL is positive across multiple sessions
- User has a funded Polymarket wallet with API credentials

## Gate condition

**This is the riskiest phase.** Only proceed when:
1. Paper trading has been running for a meaningful period with positive PnL
2. Backtesting confirms the strategy across multiple config variants
3. The false-positive labeling (Phase 5) has been used to refine alert quality
4. The user explicitly approves moving to live capital

## Modules to build

### 1. `src/poly_crawler/execution/live/adapter.py` — LiveExecutionAdapter

Concrete implementation of `ExecutionAdapter` that submits real CLOB orders.

```python
class LiveExecutionAdapter(ExecutionAdapter):
    def __init__(self, config: Config, credentials: LiveCredentials):
        self._config = config
        self._clob_client = ClobClient(
            host=config.live.clob_host,
            key=credentials.private_key,
            chain_id=config.live.chain_id,
            signature_type=POLY_PROXY,
            funder=credentials.funder_address,
        )

    async def execute_entry(self, signal: EntrySignal) -> FillResult:
        # Build and sign CLOB order
        order = self._build_order(signal, side="BUY")
        resp = await self._clob_client.post_order(order)
        return self._parse_fill(resp)

    async def execute_exit(self, signal: EntrySignal) -> FillResult:
        # Build and sign CLOB sell order
        order = self._build_order(signal, side="SELL")
        resp = await self._clob_client.post_order(order)
        return self._parse_fill(resp)
```

**Functions:**

| Function | Purpose |
|----------|---------|
| `_build_order(signal, side) -> ClobOrder` | Construct a signed CLOB order from an EntrySignal |
| `_parse_fill(resp) -> FillResult` | Parse CLOB response into FillResult |
| `_check_slippage(fill, max_slippage_pct) -> bool` | Verify fill slippage is within limit (spec §8.4) |

### 2. `src/poly_crawler/execution/live/clob_client.py` — Polymarket CLOB client

Wraps the Polymarket CLOB API for order submission. Handles authentication, signing, and order types.

**Functions:**

| Function | Purpose |
|----------|---------|
| `ClobClient.__init__(host, key, chain_id, signature_type, funder)` | Initialize with wallet credentials |
| `async post_order(order) -> dict` | Submit a signed order to the CLOB |
| `async get_order_status(order_id) -> dict` | Check fill status |
| `async cancel_order(order_id) -> dict` | Cancel an open order |
| `async get_balance() -> dict` | Check USDC balance |
| `async get_open_positions() -> dict` | Check current positions |

### 3. `src/poly_crawler/execution/live/credentials.py` — Credential management

Securely loads and manages wallet credentials. Never logs or exposes private keys.

**Functions:**

| Function | Purpose |
|----------|---------|
| `load_credentials() -> LiveCredentials` | Load from env vars or encrypted file |
| `validate_credentials(creds) -> bool` | Verify wallet is funded and authorized |

**LiveCredentials:**

```python
@dataclass
class LiveCredentials:
    private_key: str  # Never logged, never in DB
    funder_address: str  # Polymarket proxy funder
    api_key: str | None = None  # CLOB API key if required
```

### 4. `src/poly_crawler/config/schema.py` — LiveConfig

New config section for live execution settings.

```python
class LiveConfig(BaseModel):
    clob_host: str = "https://clob.polymarket.com"
    chain_id: int = 137  # Polygon mainnet
    order_type: Literal["FOK", "GTC", "GTD"] = "FOK"  # Fill-Or-Kill default
    max_retries: int = 3
    retry_delay_sec: int = 5
```

Add `live: LiveConfig = LiveConfig()` to `Config`.

### 5. Update `src/poly_crawler/engine/processor.py` — Slippage guard

Add slippage check after live fills (spec §8.4):

```python
async def _execute_action(self, action: Action) -> FillResult | None:
    if self._config.execution.mode == "live":
        fill = await self._execution.execute_entry(signal)
        if self._config.exit.max_slippage_pct is not None:
            if fill.slippage_bps > self._config.exit.max_slippage_pct * 100:
                # Slippage exceeded — log alert, don't proceed
                await self._event_logger.log_alert(
                    type="slippage_exceeded",
                    metadata={"slippage_bps": fill.slippage_bps, "limit": ...}
                )
                return None
    ...
```

### 6. Update `src/poly_crawler/main.py` — Adapter selection

Select execution adapter based on `execution.mode`:

```python
def create_execution_adapter(config, ingestion):
    mode = config.execution.mode
    if mode == "observe":
        return NoopExecutionAdapter()  # No trades
    elif mode == "paper":
        return PaperExecutionAdapter(ingestion, config)
    elif mode == "live":
        creds = load_credentials()
        return LiveExecutionAdapter(config, creds)
```

## Data flow

### Live entry

```
1. FSM produces Action(type="enter", side="yes", shares=200)
2. Engine checks execution.mode == "live"
3. LiveExecutionAdapter.execute_entry(signal)
   a. Build CLOB order: BUY 200 YES shares at market (FOK)
   b. Sign order with wallet private key
   c. Submit to CLOB API
   d. Wait for fill confirmation
   e. Parse response → FillResult(avg_price, filled_shares, slippage)
4. Check slippage guard:
   - If slippage_bps > max_slippage_pct × 100 → alert, don't proceed
5. event_logger.log_paper_trade(...)  # Still logged in paper_trades table
   - event_type="entry", our_fill_price=real_fill_price
6. Update cluster_position
7. Alert: type="entry", metadata includes "live": true
```

### Live exit

```
1. FSM produces Action(type="exit", reason="cluster_hedged")
2. LiveExecutionAdapter.execute_exit(signal)
   a. Build CLOB order: SELL 200 YES shares (FOK)
   b. Sign and submit
   c. Parse fill → FillResult
3. Check slippage guard
4. log_paper_trade(event_type="exit", reason="cluster_hedged")
5. Update cluster_position → CLOSED → WATCHING
```

## Config changes

| New key | Type | Default | Purpose |
|---------|------|---------|---------|
| `live.clob_host` | `str` | `"https://clob.polymarket.com"` | CLOB API endpoint |
| `live.chain_id` | `int` | `137` | Polygon mainnet |
| `live.order_type` | `Literal["FOK", "GTC", "GTD"]` | `"FOK"` | Order type (Fill-Or-Kill default) |
| `live.max_retries` | `int` | `3` | Retry count for failed orders |
| `live.retry_delay_sec` | `int` | `5` | Delay between retries |

Add `LiveConfig` to `schema.py` and `default.yaml`.

**Note:** `exit.max_slippage_pct` already exists (added in pre-flight fix).

## DB changes

None. Live trades are still logged to `paper_trades` (the table name is historical — it stores all trades, paper and live). Consider adding a `mode` column or using `session.mode` to distinguish.

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_live_adapter.py` | Order building from EntrySignal; fill response parsing; slippage guard logic; retry logic |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_live_execution.py` | LiveExecutionAdapter with mock CLOB client → order submission → fill parsing → slippage check; retry on failure |

**Critical:** Live tests use a **mock CLOB client**. No real orders are placed in tests. Real order testing is done manually with small amounts.

### Manual testing checklist

Before going live with real capital:

- [ ] Paper PnL is positive over multiple sessions
- [ ] Backtesting confirms strategy across config variants
- [ ] Live adapter tested with mock CLOB client
- [ ] Credentials loaded securely (env vars, not hardcoded)
- [ ] Slippage guard configured (`exit.max_slippage_pct` set)
- [ ] Start with `execution.mode: observe` → verify no trades
- [ ] Switch to `execution.mode: paper` → verify simulated trades
- [ ] Switch to `execution.mode: live` with **minimum capital**
- [ ] Monitor first live trades via dashboard
- [ ] Verify live fills match expected prices within slippage limits

## Acceptance criteria

- [ ] `LiveExecutionAdapter` implements `execute_entry` and `execute_exit`
- [ ] CLOB orders signed and submitted correctly
- [ ] Fill responses parsed into `FillResult`
- [ ] Slippage guard active when `max_slippage_pct` is set
- [ ] Credentials loaded from env vars (never hardcoded or logged)
- [ ] `execution.mode: live` selects `LiveExecutionAdapter`
- [ ] `execution.mode: observe` selects a no-op adapter (no trades)
- [ ] Live trades logged to `paper_trades` with real fill prices
- [ ] Retry logic handles transient CLOB failures
- [ ] All unit + integration tests pass (with mock CLOB)
- [ ] `ruff check` and `mypy` pass clean
- [ ] Manual testing checklist completed

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Polymarket CLOB SDK | Use `py-clob-client` (official Python SDK) or roll our own? Official SDK recommended. |
| 2 | Order type | FOK (Fill-Or-Kill) ensures full fill or nothing. GTC (Good-Till-Cancelled) leaves open orders. FOK recommended for mirroring. |
| 3 | Position sizing for live | Start with reduced `mirror_pct` (e.g. 0.1 instead of 1.0) for first live tests. Scale up gradually. |
| 4 | Kill switch | Need an emergency stop — CLI command or API endpoint to immediately close all positions and stop trading. |
| 5 | Wallet funding | How much USDC to fund the live wallet? Depends on mirror_cap_usd and number of concurrent positions. |
| 6 | Regulatory considerations | User responsibility — ensure compliance with local regulations. System provides tools, not legal advice. |
