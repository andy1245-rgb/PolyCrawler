# Phase 2 Design Decisions

**Status:** Planning; implementation has not started.  
**Scope:** Parent watcher + scoring, delivered in slices A → B → C → D.

## Agreed decisions

### RPC budget

Use a free-tier/public Polygon RPC initially. Apply a soft request-rate limit and log usage. Move to a paid provider only after the bot is profitable; paid settings must be explicit rather than inheriting free-tier assumptions.

### Multicall boundary

Use a thin, project-owned Multicall3 wrapper inside `RpcClient`. Multicall3 ABI details, contract address, encoding, decoding, and failure handling remain private to that abstraction.

No event detector, tracer, adapter, watcher, scheduler, engine, or clustering module may import `web3`, call Multicall3, or access a raw provider directly. They may use only the public methods of the applicable abstraction.

### Scheduler

Use asyncio task loops for the v0.1 watcher. Reconsider APScheduler later only if persisted schedules, misfire handling, or substantially more scheduling complexity becomes necessary.

## Intentionally unresolved

### Polling and reorgs

Block-range polling is the preferred direction, but the following must be decided together:

- confirmation depth;
- whether to rescan a recent buffer;
- behavior when a previously observed block is reorged;
- log chunk size and backoff;
- persistent versus in-memory cursor;
- free-tier and paid-tier polling profiles.

### Profit inputs

The score must use realized cashflow reconstruction, not the UI `cashPnl` field. The exact source data, treatment of BUY/SELL/REDEEM/MERGE/SPLIT, and fallback behavior remain open.

### Event identity

On-chain detection observes wallet addresses before a new `Account` row and database UUID exist. The design must choose whether to:

1. emit an address-first detection event and resolve/persist it in a watcher service; or
2. let the adapter write database rows before emitting UUID-based events.

The adapter must not silently take on database ownership without an explicit decision.

