# Phase 1 Manual Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working `poly-crawler seed` CLI that inserts parent wallets + cluster rows, lists them, and marks ignored — no chain I/O.

**Architecture:** Typer CLI → `load_config` / `init_engine` → `parent_repo` async helpers → Postgres. Address validation via `eth_utils`. Duplicates skipped with a warning.

**Tech Stack:** Typer, SQLAlchemy async, eth_utils, pytest + CliRunner, existing Phase 0 models.

---

### Task 1: RPC free-tier config clarification

- [ ] Set `rpc.budget_mode` default to `free_tier` with `max_requests_per_second: 5`
- [ ] Update docs/open-questions to say free-tier now, paid/capped later

### Task 2: Parent repository (TDD)

- [ ] Write failing `tests/unit/test_parent_repo.py` per phase1 test plan
- [ ] Implement `src/poly_crawler/db/repositories/parent_repo.py`
- [ ] Add `session_scope` helper on engine for CLI use
- [ ] Make unit tests pass on SQLite

### Task 3: Seed CLI (TDD)

- [ ] Write failing integration tests for seed CLI
- [ ] Implement `cli.py` seed/list/ignore/from-file
- [ ] Make integration tests pass against Postgres

### Task 4: Docs + acceptance

- [ ] Mark Phase 1 complete in phase docs / `_index.md`
- [ ] Run full lint/mypy/pytest; commit and push
