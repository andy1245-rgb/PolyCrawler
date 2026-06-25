# Tech Stack

**Source:** spec.md §15

---

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python ≥3.11 | Full control, no inherited debt |
| Web framework | FastAPI | Async-native, great DX |
| ORM | SQLAlchemy 2.0 (async) | Mature async support |
| DB driver | asyncpg | Fastest async Postgres driver |
| DB migrations | Alembic | Standard for SQLAlchemy |
| Config | Pydantic + Pydantic-Settings | Validation + env var loading |
| YAML | PyYAML | Config file format |
| Blockchain | web3.py | Ethereum/Polygon RPC client |
| HTTP | httpx | Async HTTP for Data API |
| Scheduling | APScheduler | Periodic task orchestration |
| Testing | pytest + pytest-asyncio + pytest-cov | Standard Python test stack |
| Linting | ruff | Fast Python linter |
| Typing | mypy | Static type checking |

## Key architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Ingestion | Polling-first via abstract adapter | WebSocket swap-in later without touching engine |
| Foundation | Build from scratch in Python | Full control, no inherited debt |
| Async | SQLAlchemy async + asyncpg + asyncio | End-to-end async, aligns with FastAPI |
| Adapters | IngestionAdapter + ExecutionAdapter | Drop-in replacement for WS ingestion and live execution |
