# Project Structure

**Source:** docs/architecture.md §1

---

```
poly-crawler/
├── pyproject.toml                        # Dependencies, metadata
├── Makefile                              # Dev convenience (lint, test, run, migrate)
├── README.md                             # Project status & quick start
├── alembic.ini                           # Migration config
├── alembic/
│   └── versions/
│       └── 0001_initial.py               # Creates all 11 tables
├── config/
│   ├── default.yaml                      # Baseline config (spec §14)
│   └── production.yaml                   # Prod overrides template
├── docs/                                 # Documentation (28 .md files)
├── scripts/
│   ├── dev.ps1                           # PowerShell dev commands (Windows)
│   └── validate_schema.py                # alembic check wrapper
├── src/
│   └── poly_crawler/
│       ├── __init__.py
│       ├── main.py                       # FastAPI app, lifespan, /health
│       ├── config/                       # Config loading & schema
│       │   ├── __init__.py               # Public exports
│       │   ├── loader.py                 # YAML + env → Pydantic
│       │   └── schema.py                 # 13 Pydantic models
│       ├── db/                           # Database layer
│       │   ├── __init__.py               # Public exports
│       │   ├── base.py                   # DeclarativeBase + mixins
│       │   ├── engine.py                 # Async engine, session factory
│       │   └── models/                   # 11 SQLAlchemy ORM models
│       │       ├── parent.py             # parents table
│       │       ├── account.py            # accounts table
│       │       ├── cluster.py            # clusters table
│       │       ├── cluster_position.py   # cluster_positions table
│       │       ├── alert.py              # alerts table
│       │       ├── paper_trade.py        # paper_trades table
│       │       ├── balance_snapshot.py   # sibling_balance_snapshots table
│       │       ├── session.py            # sessions table
│       │       ├── config_snapshot.py    # config_snapshots table
│       │       ├── rpc_log.py            # rpc_logs table
│       │       └── backtest_run.py       # backtest_runs table
│       ├── ingestion/                    # Blockchain data ingestion
│       │   ├── __init__.py               # (Phase 1)
│       │   └── polling/
│       │       └── __init__.py           # (Phase 1)
│       ├── clustering/                   # Parent tracing & scoring
│       │   └── __init__.py               # (Phase 2)
│       ├── engine/                       # Core processing
│       │   └── __init__.py               # (Phase 3)
│       ├── execution/                    # Trade execution
│       │   ├── __init__.py               # (Phase 3)
│       │   └── paper/
│       │       └── __init__.py           # (Phase 3)
│       ├── analytics/                    # Sessions & reporting
│       │   └── __init__.py               # (Phase 4)
│       ├── api/                          # FastAPI routes
│       │   ├── __init__.py               # (Phase 5)
│       │   └── routes/
│       │       └── __init__.py           # (Phase 5)
│       └── scheduler/                    # Task orchestration
│           └── __init__.py               # (Phase 6)
└── tests/
    ├── __init__.py
    ├── conftest.py                       # Async engine, session, factory fixtures
    ├── unit/
    │   └── __init__.py                   # (Phase 1+)
    ├── integration/
    │   └── __init__.py                   # (Phase 1+)
    └── fixtures/
        ├── __init__.py
        ├── labeled_wallets.json           # Parent→account→cluster test data (Phase 1+)
        ├── sample_events.json             # Fund, birth, trade event sequences (Phase 1+)
        └── sample_orderbook.json          # CLOB bid/ask levels for paper fill tests (Phase 3+)
```

## Module status key

| Marker | Meaning |
|--------|---------|
| No annotation | Implemented and present on disk |
| `(Phase N)` | Not yet implemented — planned for Phase N |
| `(Phase N+)` | Planned for Phase N or later (depends on earlier phases) |
