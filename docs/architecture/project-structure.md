# Project Structure

**Source:** docs/architecture.md §1

---

```
poly-crawler/
├── pyproject.toml                        # Dependencies, metadata
├── alembic.ini                           # Migration config
├── alembic/
│   └── versions/                         # Auto-generated migrations
├── config/
│   ├── default.yaml                      # Baseline config (spec §14)
│   └── production.yaml                   # Prod overrides
├── docs/                                 # Documentation
├── src/
│   └── poly_crawler/
│       ├── __init__.py
│       ├── main.py                       # App lifecycle, startup/shutdown
│       ├── config/                       # Config loading & schema
│       │   ├── loader.py                 # YAML + env → Pydantic
│       │   └── schema.py                 # Config models
│       ├── db/                           # Database layer
│       │   ├── engine.py                 # Async engine, session factory
│       │   └── models/                   # SQLAlchemy ORM (12 tables)
│       ├── ingestion/                    # Blockchain data ingestion
│       │   ├── base.py                   # Abstract IngestionAdapter
│       │   └── polling/                  # Default polling impl
│       ├── clustering/                   # Parent tracing & scoring
│       │   ├── tracer.py
│       │   ├── scorer.py
│       │   └── discovery.py
│       ├── engine/                       # Core processing
│       │   ├── processor.py              # Main poll cycle
│       │   ├── state_machine.py          # Cluster×market FSM
│       │   ├── net_calculator.py
│       │   ├── entry_rules.py
│       │   ├── exit_rules.py
│       │   ├── hedge_filter.py
│       │   └── reentry.py
│       ├── execution/                    # Trade execution
│       │   ├── base.py                   # Abstract ExecutionAdapter
│       │   └── paper/                    # Default paper impl
│       │       └── orderbook_walk.py     # Fill model
│       ├── analytics/                    # Sessions & reporting
│       ├── api/                          # FastAPI routes
│       └── scheduler/                    # Task orchestration
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```
