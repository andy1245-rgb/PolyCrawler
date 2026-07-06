# Phase 0 — Bootstrap

**Status:** ✅ Complete
**Prerequisites:** None
**Human-readable docs:** [purpose.md](../overview/purpose.md), [tech-stack.md](../reference/tech-stack.md), [configuration.md](../reference/configuration.md)

---

## Goal

Establish the project skeleton: package structure, configuration system, database models, migration tooling, application entry point, and test infrastructure. No domain logic — just the foundation every subsequent phase builds on.

---

## Behavioral specification

Phase 0 implements **infrastructure only**. No trading, discovery, or chain logic yet. The following must exist so later phases can plug in:

### Config system

- Layered load: `config/default.yaml` → environment variables → optional user override file.
- Pydantic validation for all config sections (discovery, entry, exit, review, execution, paper, conflict, position, watch, alerts, retention).
- See [configuration.md](../reference/configuration.md) for all keys.

### Database

- PostgreSQL with async SQLAlchemy.
- 11 tables: `parents`, `accounts`, `clusters`, `cluster_positions`, `sibling_balance_snapshots`, `alerts`, `paper_trades`, `sessions`, `config_snapshots`, `rpc_logs`, `backtest_runs`.
- Alembic migrations; `alembic upgrade head` creates all tables.
- See [database-schema.md](../reference/database-schema.md).

### Application entry

- FastAPI app with lifespan (init/close DB engine).
- `GET /health` returns `{"status": "ok"}`.
- Typer CLI stub (`poly-crawler seed`, `poly-crawler run`).

### Tech stack (v0.1)

| Layer | Choice |
|-------|--------|
| Language | Python |
| Database | PostgreSQL |
| API | FastAPI |
| Chain | Polygon RPC + Polymarket Data API (wired in Phase 2) |
| Jobs | Asyncio scheduler (Phase 2) |

---

## Implementation

### What was delivered

| Deliverable | Key files |
|-------------|-----------|
| Package structure | `src/poly_crawler/` tree |
| Config schema (13 Pydantic models) | `config/schema.py`, `config/default.yaml` |
| 11 SQLAlchemy ORM models | `db/models/*.py` |
| Alembic initial migration | `alembic/versions/0001_initial.py` |
| FastAPI app + `/health` | `main.py` |
| Test conftest + fixtures | `tests/conftest.py`, `tests/fixtures/*.json` |
| Build tooling | `Makefile`, `scripts/validate_schema.py` |

Full detail: [phase0-complete.md](../reference/phase0-complete.md).

### Stub directories (filled in later phases)

| Module | Phase |
|--------|-------|
| `ingestion/` | 2 |
| `clustering/` | 2 (scorer), 7 (discovery) |
| `engine/` | 3a |
| `execution/` | 3b, 8 |
| `analytics/` | 3b, 5, 6 |
| `api/` | 5 |
| `scheduler/` | 2 |

---

## Config changes

All config sections defined in Phase 0. Pre-flight fixes applied before Phase 1:

- `ExitConfig`: `max_slippage_pct`, `add_on_repeat_buy`, `notify_on_repeat_buy`, `tp_sl_suspend_mirror_until_flat`
- Top-level `rpc_url` for Polygon RPC

---

## DB changes

Initial migration only — no further schema changes in Phase 0.

---

## Test plan

- `pip install -e ".[dev]"` succeeds
- `alembic upgrade head` creates all 11 tables
- `uvicorn poly_crawler.main:app` starts; `/health` returns 200
- `ruff check` and `mypy` pass
- `python scripts/validate_schema.py` reports no drift

---

## Acceptance criteria

- [x] Package installable with dev dependencies
- [x] All 11 tables created via Alembic
- [x] FastAPI health endpoint works
- [x] Config loads and validates from YAML + env
- [x] All ORM models importable from `poly_crawler.db.models`
- [x] Lint and type checks pass

---

## Open decisions

None — Phase 0 is complete.
