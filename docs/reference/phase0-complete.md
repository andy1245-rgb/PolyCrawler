# Phase 0 — Bootstrap Deliverables

**Source:** [implementation-phases.md](./implementation-phases.md) → Phase 0

---

Phase 0 established the project skeleton. Below is every deliverable with its location, purpose, API surface, and usage notes.

---

## 1. Application Entry Point

**File:** `src/poly_crawler/main.py`

The FastAPI application factory. This is the process that runs when you start the crawler.

### What it does

- Defines a `lifespan` async context manager that calls `init_engine(config)` on startup and `close_engine()` on shutdown
- Exports a module-level `app: FastAPI` instance

### API

| Route | Method | Response |
|-------|--------|----------|
| `/health` | GET | `{"status": "ok"}` |

### Usage

```bash
# Development (auto-reload on file changes)
uvicorn poly_crawler.main:app --reload

# Production
uvicorn poly_crawler.main:app --host 0.0.0.0 --port 8000
```

### Startup sequence

1. `load_config()` reads `config/default.yaml` → environment overrides → user override → validated Pydantic model
2. `init_engine(config)` creates the async SQLAlchemy engine with connection pooling (pool_size=5, max_overflow=10)
3. FastAPI begins serving requests

### Shutdown sequence

1. `close_engine()` disposes the engine, draining all connections
2. Task cancellation propagates through running poll cycles

### Dependencies

| Import | Purpose |
|--------|---------|
| `poly_crawler.config.load_config` | Loads and validates configuration |
| `poly_crawler.db.init_engine` | Creates async engine and session factory |
| `poly_crawler.db.close_engine` | Disposes engine on shutdown |
| `FastAPI` / `JSONResponse` | HTTP framework |

---

## 2. Production Configuration Overrides

**File:** `config/production.yaml`

A template file that layers on top of `config/default.yaml`. Values here override the defaults; environment variables (`POLY_*`) override both.

### What it overrides

| Key | Default | Production | Rationale |
|-----|---------|------------|-----------|
| `execution.mode` | `paper` | `paper` | Explicit safe default — change to `live` only after validation |
| `sessions.private_default` | `false` | `true` | Production sessions private by default |
| `retention.raw_trades_days` | `90` | `365` | Longer retention for audit |
| `alerts.channels` | `["dashboard"]` | Dashboard + commented Telegram/Discord | Uncomment when credentials configured |

### Usage

```bash
# Apply production overrides at startup
POLY_CONFIG=config/production.yaml uvicorn poly_crawler.main:app
```

### Loading order (last wins)

1. `config/default.yaml` — baseline
2. Environment variables (`POLY_DISCOVERY_MIN_SIBLING_COUNT=3`)
3. File referenced by `POLY_CONFIG` environment variable (e.g., `config/production.yaml`)
4. Pydantic validation rejects invalid combinations

---

## 3. Initial Database Migration

**File:** `alembic/versions/0001_initial.py`

Creates all 11 tables in a single migration. This is the schema that every subsequent migration builds on.

### Tables created (in order)

| # | Table | Depends on | Key columns |
|---|-------|-----------|-------------|
| 1 | `parents` | — | `chain_address` (unique, indexed), `is_ignored` (indexed), `metadata` (JSONB) |
| 2 | `config_snapshots` | — | `config_json` (JSONB) |
| 3 | `sessions` | — | `mode`, `review_mode`, `config_snapshot` (JSONB), `status` |
| 4 | `accounts` | `parents` | `polymarket_address` (unique), `parent_id` (FK CASCADE, indexed), `watch_status` (indexed) |
| 5 | `clusters` | `parents` | `parent_id` (FK CASCADE, unique), `cluster_score`, `score_variant` |
| 6 | `cluster_positions` | `clusters`, `config_snapshots` | `state` (indexed), `net_exposure` (BIGINT), `uq_cluster_position` unique constraint |
| 7 | `alerts` | `parents`, `accounts`, `clusters` | `alert_type` (indexed), `is_false_positive` (indexed) |
| 8 | `paper_trades` | `cluster_positions`, `sessions`, `accounts` | `event_type`, `our_shares` (BIGINT), `slippage_bps` |
| 9 | `sibling_balance_snapshots` | `accounts`, `clusters` | `account_id` (indexed), `yes_shares`, `no_shares` (BIGINT) |
| 10 | `rpc_logs` | — | `method`, `latency_ms`, `error` |
| 11 | `backtest_runs` | `sessions` | `config_snapshot` (JSONB), `score_variant`, `status` |

### PostgreSQL-specific features used

- `UUID` — primary keys, foreign keys
- `JSONB` — flexible metadata, config snapshots, market tags
- `BIGINT` — share/exposure counters (up to 9.2 × 10¹⁸)
- `DOUBLE PRECISION` — prices, scores, USD amounts
- `gen_random_uuid()` — server-side UUID generation

### Usage

```bash
# Apply migration (creates all tables)
alembic upgrade head

# Roll back last migration
alembic downgrade -1

# Verify no schema drift
alembic check
```

### Revision metadata

| Field | Value |
|-------|-------|
| `revision` | `0001` |
| `down_revision` | `None` (first migration) |
| `create_date` | 2026-06-28 |

---

## 4. Test Infrastructure

### conftest.py

**File:** `tests/conftest.py`

Shared pytest fixtures for all test files. Uses an in-memory SQLite database (`sqlite+aiosqlite://`) so tests run without Postgres.

#### Fixtures

| Fixture | Scope | Yields | Purpose |
|---------|-------|--------|---------|
| `engine` | function | `AsyncEngine` | In-memory SQLite with all tables created |
| `session` | function | `AsyncSession` | Transactional session backed by `engine` |

#### Factory fixtures

These return keyword-argument dicts with sensible defaults. Pass them to model constructors:

```python
async def test_create_parent(session, parent_kwargs):
    parent = Parent(**parent_kwargs)
    session.add(parent)
    await session.commit()
    assert parent.chain_address == "0x" + "a" * 40
```

| Fixture | Defaults |
|---------|----------|
| `parent_kwargs` | UUID id, chain_address `0xaaaa…`, empty metadata |
| `account_kwargs` | UUID id, address `0xbbbb…`, linked to parent fixture, empty metadata |
| `cluster_kwargs` | UUID id, linked to parent fixture, score 0.0 |
| `session_kwargs` | UUID id, mode `paper`, review_mode `manual`, empty config, `running` |
| `config_snapshot_kwargs` | UUID id, empty config_json |

### Test data fixtures

**Directory:** `tests/fixtures/`

| File | Format | Purpose |
|------|--------|---------|
| `labeled_wallets.json` | JSON | One known parent with 3 siblings, cluster_score 18.3 |
| `sample_events.json` | JSON array | 3 events: fund (5k USD), birth (new account), trade (1k yes shares at 0.45) |
| `sample_orderbook.json` | JSON | Bid/ask levels for Yes and No on a sample market |

Use these in integration tests:

```python
import json

def test_load_fixtures():
    with open("tests/fixtures/sample_events.json") as f:
        events = json.load(f)
    assert len(events) == 3
```

---

## 5. Build Tooling

### Makefile

**File:** `Makefile`

GNU Make targets for common development tasks. Requires `make` (available on Linux, macOS, WSL).

| Target | Command | Purpose |
|--------|---------|---------|
| `install` | `pip install -e ".[dev]"` | Install package with dev dependencies |
| `lint` | `ruff check src/ tests/` | Check code style |
| `typecheck` | `mypy src/` | Static type checking |
| `test` | `pytest -v` | Run all tests |
| `test-cov` | `pytest --cov=… --cov-report=term-missing` | Tests with coverage report |
| `migrate` | `alembic upgrade head` | Apply pending migrations |
| `db-up` | `alembic revision --autogenerate -m "msg"` | Generate new migration (set `msg=`) |
| `db-down` | `alembic downgrade -1` | Roll back last migration |
| `run` | `uvicorn poly_crawler.main:app --reload` | Start dev server |
| `dev` | lint → typecheck → test | Full pre-commit validation |

Full pipeline before committing:

```bash
make dev
```

### dev.ps1

**File:** `scripts/dev.ps1`

PowerShell equivalent of the Makefile for Windows-native development.

```powershell
.\scripts\dev.ps1 install
.\scripts\dev.ps1 lint
.\scripts\dev.ps1 test
.\scripts\dev.ps1 run
```

### validate_schema.py

**File:** `scripts/validate_schema.py`

Runs `alembic check` to compare ORM models against the actual database schema. Exits with code 0 if in sync, 1 if drift detected.

```bash
python scripts/validate_schema.py
```

Use this in CI pipelines after running `alembic upgrade head` to catch missing autogenerated migrations.

---

## 6. README Update

**File:** `README.md`

The status line was updated from:

> **Status:** v0.1.5 — specification only. Implementation not started.

to:

> **Status:** v0.1.5 — Phase 0 (bootstrap) complete. Config schema, DB models, Alembic migrations, test infrastructure, and app entry point are in place. Moving to Phase 1 (discovery engine).

---

## File inventory — Phase 0 additions

| # | File | Lines | Type |
|---|------|-------|------|
| 1 | `src/poly_crawler/main.py` | 28 | Source |
| 2 | `config/production.yaml` | 18 | Config |
| 3 | `alembic/versions/0001_initial.py` | 191 | Migration |
| 4 | `tests/conftest.py` | 69 | Test infra |
| 5 | `tests/fixtures/__init__.py` | 1 | Test data (package marker) |
| 6 | `Makefile` | 29 | Build |
| 7 | `scripts/dev.ps1` | 31 | Build |
| 8 | `scripts/validate_schema.py` | 23 | Build |
| 9 | `README.md` | 22 (1 changed) | Docs |

> **Note:** `tests/fixtures/labeled_wallets.json`, `sample_events.json`, and `sample_orderbook.json` are **planned for Phases 1–3** (see [project-structure.md](../architecture/project-structure.md)). Only the `__init__.py` package marker was created in Phase 0.

---

## What Phase 0 now delivers (vs the spec)

| Phase 0 deliverable | Status | Files |
|---------------------|--------|-------|
| Repository structure | ✅ Complete | All directories & package stubs |
| `pyproject.toml` | ✅ Complete | Dependencies, tool configs |
| Config schema + loader | ✅ Complete | `config/schema.py`, `config/loader.py`, `config/default.yaml` | |
| All 11 DB models | ✅ Complete | `src/poly_crawler/db/models/*.py` |
| Alembic setup | ✅ Complete | `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial.py` |
| Application entry point | ✅ Complete | `src/poly_crawler/main.py` |
| Test infrastructure | ✅ Complete (conftest + package marker; fixture JSON files planned for Phases 1–3) | `tests/conftest.py`, `tests/fixtures/__init__.py` |
| Build tooling | ✅ Complete | `Makefile`, `scripts/dev.ps1`, `scripts/validate_schema.py` |
| Production config | ✅ Complete | `config/production.yaml` |
| Documentation | ✅ Complete | `docs/reference/phase0-complete.md` |
