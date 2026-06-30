# Project Structure

**Source:** docs/architecture.md §1

---

```
poly-crawler/
├── pyproject.toml                        # Dependencies, metadata, CLI entry point
├── Makefile                              # Dev convenience (lint, test, run, migrate)
├── README.md                             # Project status & quick start
├── alembic.ini                           # Migration config
├── alembic/
│   └── versions/
│       └── 0001_initial.py               # Creates all 11 tables
├── config/
│   ├── default.yaml                      # Baseline config (spec §14)
│   └── production.yaml                   # Prod overrides template
├── docs/                                 # Documentation
│   ├── _index.md                         # Master doc index
│   ├── architecture.md                   # Full technical architecture
│   ├── architecture/                     # Architecture sub-docs
│   │   ├── project-structure.md          # This file
│   │   ├── component-interfaces.md       # IngestionAdapter, ExecutionAdapter, Engine
│   │   └── document-history.md           # Spec version changelog
│   ├── phases/                           # Phase-by-phase implementation docs
│   │   ├── _index.md                     # Master phase index + dependency graph
│   │   ├── phase0-bootstrap.md           # ✅ Complete
│   │   ├── phase1-manual-seed.md         # CLI seeding, parent/cluster creation
│   │   ├── phase2-parent-watcher.md      # Ingestion, polling, scoring, scheduler
│   │   ├── phase3a-engine-core.md        # FSM, net calc, entry/exit rules
│   │   ├── phase3b-paper-execution.md    # Orderbook walk, session/logger
│   │   ├── phase4-reconciliation.md      # Balance multicall, reconciliation
│   │   ├── phase5-dashboard-api.md       # FastAPI routes
│   │   ├── phase6-backtesting.md         # Backtest runner, score validation
│   │   ├── phase7-auto-discovery.md      # Auto-flagging pipeline
│   │   └── phase8-live-execution.md      # Live CLOB execution
│   ├── overview/                         # Purpose, glossary, account types
│   ├── discovery/                        # Clustering, new-account detection
│   ├── protocols/                        # Position FSM, entry, exit, review
│   ├── execution/                        # Modes, paper fill model
│   ├── operations/                       # Alerts, sessions, end-to-end flow
│   └── reference/                        # Config, schema, API, tech stack, etc.
├── scripts/
│   ├── dev.ps1                           # PowerShell dev commands (Windows)
│   └── validate_schema.py                # alembic check wrapper
├── src/
│   └── poly_crawler/
│       ├── __init__.py
│       ├── main.py                       # FastAPI app, lifespan, /health
│       ├── cli.py                        # (Phase 1) CLI entry point — seed, discover
│       ├── config/                       # Config loading & schema
│       │   ├── __init__.py               # Public exports
│       │   ├── loader.py                 # YAML + env → Pydantic
│       │   └── schema.py                 # Pydantic config models (all spec §14 keys)
│       ├── db/                           # Database layer
│       │   ├── __init__.py               # Public exports
│       │   ├── base.py                   # DeclarativeBase + mixins
│       │   ├── engine.py                 # Async engine, session factory
│       │   ├── models/                   # 11 SQLAlchemy ORM models
│       │   │   ├── __init__.py           # Re-exports all 11 models
│       │   │   ├── parent.py             # parents table
│       │   │   ├── account.py            # accounts table
│       │   │   ├── cluster.py            # clusters table
│       │   │   ├── cluster_position.py   # cluster_positions table
│       │   │   ├── alert.py              # alerts table
│       │   │   ├── paper_trade.py        # paper_trades table
│       │   │   ├── balance_snapshot.py   # sibling_balance_snapshots table
│       │   │   ├── session.py            # sessions table
│       │   │   ├── config_snapshot.py    # config_snapshots table
│       │   │   ├── rpc_log.py            # rpc_logs table
│       │   │   └── backtest_run.py       # backtest_runs table
│       │   └── repositories/             # (Phase 1) Repository layer
│       │       └── parent_repo.py        # (Phase 1) Parent/cluster DB operations
│       ├── ingestion/                    # Blockchain data ingestion
│       │   ├── __init__.py               # (Phase 2)
│       │   ├── base.py                   # (Phase 2) IngestionAdapter ABC + RawEvent
│       │   └── polling/                  # (Phase 2) Polling implementation
│       │       ├── __init__.py           # (Phase 2)
│       │       ├── adapter.py            # (Phase 2) PollingIngestionAdapter
│       │       ├── rpc_client.py         # (Phase 2) web3.py Polygon RPC wrapper
│       │       ├── data_api.py           # (Phase 2) Polymarket Data API client
│       │       ├── event_detector.py     # (Phase 2) FUND/BIRTH/TRADE detection
│       │       └── multicall.py          # (Phase 4) Multicall3 batch reads
│       ├── clustering/                   # Parent tracing & scoring
│       │   ├── __init__.py               # (Phase 2)
│       │   ├── tracer.py                 # (Phase 2) Parent → account tracing
│       │   ├── scorer.py                 # (Phase 2) Score variants A/B/C
│       │   └── discovery.py              # (Phase 2 basic, Phase 7 full) Parent flagging
│       ├── engine/                       # Core processing
│       │   ├── __init__.py               # (Phase 3a)
│       │   ├── processor.py              # (Phase 3a) Main poll cycle
│       │   ├── state_machine.py          # (Phase 3a) Position FSM
│       │   ├── net_calculator.py         # (Phase 3a) Net exposure, mirror targets
│       │   ├── entry_rules.py            # (Phase 3a) §7.1 entry conditions
│       │   ├── exit_rules.py             # (Phase 3a) §8 exit conditions
│       │   ├── hedge_filter.py           # (Phase 3a) §7.5 hedge modes
│       │   ├── reentry.py                # (Phase 3a) §7.6 follow re-entry
│       │   └── reconciliation.py         # (Phase 4) Balance reconciliation
│       ├── execution/                    # Trade execution
│       │   ├── __init__.py               # (Phase 3b)
│       │   ├── base.py                   # (Phase 3b) ExecutionAdapter ABC
│       │   ├── paper/                    # (Phase 3b) Paper implementation
│       │   │   ├── __init__.py           # (Phase 3b)
│       │   │   ├── adapter.py            # (Phase 3b) PaperExecutionAdapter
│       │   │   └── orderbook_walk.py     # (Phase 3b) VWAP fill model
│       │   └── live/                     # (Phase 8) Live implementation
│       │       ├── __init__.py           # (Phase 8)
│       │       ├── adapter.py            # (Phase 8) LiveExecutionAdapter
│       │       ├── clob_client.py        # (Phase 8) Polymarket CLOB client
│       │       └── credentials.py        # (Phase 8) Wallet credential management
│       ├── analytics/                    # Sessions & reporting
│       │   ├── __init__.py               # (Phase 3b)
│       │   ├── session_manager.py        # (Phase 3b) Session lifecycle
│       │   ├── event_logger.py           # (Phase 3b) Trade/alert persistence
│       │   ├── aggregator.py             # (Phase 5) Global rollups
│       │   ├── backtest_runner.py        # (Phase 6) Backtest executor
│       │   ├── backtest_stats.py         # (Phase 6) Result aggregation
│       │   └── event_replay.py           # (Phase 6) Historical event loader
│       ├── api/                          # FastAPI routes
│       │   ├── __init__.py               # (Phase 5)
│       │   ├── app.py                    # (Phase 5) FastAPI app factory
│       │   ├── schemas.py                # (Phase 5) Pydantic response models
│       │   └── routes/                   # (Phase 5)
│       │       ├── __init__.py           # (Phase 5)
│       │       ├── alerts.py             # (Phase 5) Alert routes
│       │       ├── positions.py          # (Phase 5) Position routes
│       │       ├── sessions.py           # (Phase 5) Session routes
│       │       ├── config.py             # (Phase 5) Config routes
│       │       └── stats.py              # (Phase 5) Analytics routes
│       └── scheduler/                    # Task orchestration
│           ├── __init__.py               # (Phase 2)
│           ├── manager.py                # (Phase 2) asyncio task manager
│           └── tasks.py                  # (Phase 2) Periodic job definitions
└── tests/
    ├── __init__.py
    ├── conftest.py                       # Async engine, session, factory fixtures
    ├── unit/
    │   └── __init__.py                   # (Phase 2+)
    ├── integration/
    │   └── __init__.py                   # (Phase 2+)
    └── fixtures/
        ├── __init__.py
        ├── labeled_wallets.json           # Parent→account→cluster test data
        ├── sample_events.json             # Fund, birth, trade event sequences
        └── sample_orderbook.json          # CLOB bid/ask levels for paper fill tests
```

## Module status key

| Marker | Meaning |
|--------|---------|
| No annotation | Implemented and present on disk |
| `(Phase N)` | Not yet implemented — planned for Phase N |
| `(Phase N basic, Phase M full)` | Partial implementation in Phase N, completed in Phase M |
