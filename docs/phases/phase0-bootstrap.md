# Phase 0 — Bootstrap

**Source:** spec.md §16 | docs/architecture.md §12
**Status:** ✅ Complete

---

## Goal

Establish the project skeleton: package structure, configuration system, database models, migration tooling, application entry point, and test infrastructure. No domain logic — just the foundation every subsequent phase builds on.

## What was delivered

| Deliverable | Status | Key files |
|-------------|--------|-----------|
| Package structure with all stub directories | ✅ | `src/poly_crawler/` tree |
| `pyproject.toml` with deps + tool config | ✅ | `pyproject.toml` |
| Config schema (13 Pydantic models) | ✅ | `config/schema.py` |
| Config loader (YAML → env → override) | ✅ | `config/loader.py`, `config/default.yaml` |
| 11 SQLAlchemy ORM models | ✅ | `db/models/*.py` |
| Async engine + session factory | ✅ | `db/engine.py` |
| Declarative base + mixins | ✅ | `db/base.py` |
| Alembic initial migration (all 11 tables) | ✅ | `alembic/versions/0001_initial.py` |
| FastAPI app with lifespan + `/health` | ✅ | `main.py` |
| Test conftest (in-memory SQLite + factories) | ✅ | `tests/conftest.py` |
| 3 JSON fixture files | ✅ | `tests/fixtures/*.json` |
| Build tooling (Makefile, dev.ps1, validate_schema) | ✅ | `Makefile`, `scripts/` |
| Production config override template | ✅ | `config/production.yaml` |

For full Phase 0 detail, see [phase0-complete.md](../reference/phase0-complete.md).

## What exists on disk

### Implemented modules (with real code)

| Module | Files | Purpose |
|--------|-------|---------|
| `config/` | `__init__.py`, `schema.py`, `loader.py` | Pydantic config models + YAML/env layered loader |
| `db/` | `__init__.py`, `base.py`, `engine.py` | Declarative base, UUID/Timestamp mixins, async engine |
| `db/models/` | `__init__.py` + 11 model files | All ORM models (parents, accounts, clusters, positions, alerts, trades, snapshots, sessions, config_snapshots, rpc_logs, backtest_runs) |
| `main.py` | — | FastAPI app factory with startup/shutdown lifespan |

### Empty stubs (phase markers)

| Module | Planned phase |
|--------|---------------|
| `ingestion/`, `ingestion/polling/` | Phase 2 |
| `clustering/` | Phase 2 (scorer), Phase 7 (full discovery) |
| `engine/` | Phase 3a |
| `execution/`, `execution/paper/` | Phase 3b |
| `analytics/` | Phase 3b (session/logger), Phase 5 (aggregator) |
| `api/`, `api/routes/` | Phase 5 |
| `scheduler/` | Phase 2 |

## Known gaps to fix before Phase 1

| Issue | Details |
|-------|---------|
| Missing `aiosqlite` dependency | `tests/conftest.py` uses `sqlite+aiosqlite://` but `aiosqlite` is not in `pyproject.toml` dev deps |
| No CLI entry point | `[project.scripts]` not defined; only way to run is `uvicorn` |
| Missing config keys | Spec §14 references `exit.maxSlippagePct`, `exit.addOnRepeatBuy`, `exit.notifyOnRepeatBuy`, `exit.tpSlSuspendMirrorUntilFlat` — not yet in `schema.py` or `default.yaml` |
| No RPC provider config | No `rpc_url` / `database_url` in config schema; engine defaults to `localhost:5432` |
| Zero test functions | conftest + fixtures exist but no actual `test_*.py` files |

## Acceptance criteria (all met)

- [x] `pip install -e ".[dev]"` succeeds
- [x] `alembic upgrade head` creates all 11 tables
- [x] `uvicorn poly_crawler.main:app` starts and `/health` returns 200
- [x] `ruff check src/ tests/` passes
- [x] `mypy src/` passes
- [x] `python scripts/validate_schema.py` reports no drift
- [x] Config loads from YAML, env vars override, Pydantic validates
- [x] All 11 models importable from `poly_crawler.db.models`
