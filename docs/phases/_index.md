# Implementation Phases — Master Index

**Development specs:** each phase doc below is self-contained (behavior + implementation).
**Human onboarding:** [docs/_index.md](../_index.md) — glossary, protocols, operations.

---

## Phase overview

| Phase | Name | Status | Key deliverable |
|-------|------|--------|-----------------|
| [0](phase0-bootstrap.md) | Bootstrap | ✅ Complete | Repo skeleton, config, DB models, Alembic, FastAPI, test infra |
| [1](phase1-manual-seed.md) | Manual seed | ⬜ Not started | CLI to seed parent wallets + create cluster rows |
| [2](phase2-parent-watcher.md) | Parent watcher + scoring | ⬜ Not started | IngestionAdapter, polling, event detection, scheduler, scorer |
| [3a](phase3a-fsm-and-net.md) | FSM + net calculator | ⬜ Not started | Position FSM, net calc, processor orchestration |
| [3a](phase3a-trading-rules.md) | Trading rules | ⬜ Not started | Entry, exit, hedge filter, re-entry, review gates |
| [3b](phase3b-paper-execution.md) | Paper execution | ⬜ Not started | ExecutionAdapter, orderbook walk, session manager, event logger |
| [4](phase4-reconciliation.md) | Reconciliation + RPC batching | ⬜ Not started | Balance multicall, reconciliation scanner, RPC log cleanup |
| [5](phase5-dashboard-api.md) | Dashboard API | ⬜ Not started | FastAPI routes for alerts, positions, sessions, config |
| [6](phase6-backtesting.md) | Backtesting | ⬜ Not started | Backtest runner, score validation, historical replay |
| [7](phase7-auto-discovery.md) | Auto-discovery | ⬜ Not started | Full discovery pipeline, auto-flagging with minClusterScore |
| [8](phase8-live-execution.md) | Live execution | ⬜ Not started | Live ExecutionAdapter, real CLOB order signing |

---

## Dependency graph

```
                    ┌──────────┐
                    │ Phase 0  │ ✅ DONE
                    │ Bootstrap│
                    └────┬─────┘
                         │
                    ┌────▼─────┐
                    │ Phase 1  │
                    │Seed (CLI)│
                    └────┬─────┘
                         │
               ┌─────────▼──────────┐
               │     Phase 2        │
               │ Parent Watcher     │
               │ + Scoring          │
               └─────────┬──────────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
 ┌────────▼─────────┐       ┌──────────▼──────────┐
 │ Phase 3a (FSM)   │       │ Phase 3a (Rules)    │
 │ fsm-and-net      │◄─────►│ trading-rules       │
 └────────┬─────────┘       └──────────┬──────────┘
          └──────────────┬──────────────┘
                         │
               ┌─────────▼──────────┐
               │     Phase 3b       │
               │ Paper Execution    │
               └─────────┬──────────┘
                         │
               ┌─────────▼──────────┐
               │     Phase 4        │
               │ Reconciliation     │
               └─────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐
   │  Phase 5    │ │ Phase 6   │ │  Phase 7   │
   │ Dashboard   │ │Backtesting│ │Auto-Discover│
   └─────────────┘ └───────────┘ └─────┬──────┘
                                      │
                               ┌──────▼──────┐
                               │  Phase 8    │
                               │ Live Exec   │
                               └─────────────┘
```

### Parallelization

- **Phase 2 scoring** — pure math; develop alongside ingestion adapter.
- **Phase 3a FSM + Phase 3a rules** — can develop in parallel (rules are pure functions; FSM uses a no-op execution stub until 3b).
- **Phase 5 (API)** — can start in parallel with Phase 4.
- **Phase 6 and Phase 7** — independent; both need Phase 3b complete.

### Critical path

**Phase 1 → 2 → 3a (both docs) → 3b → 4**

---

## Phase doc conventions

Every phase doc uses this structure:

| Section | Content |
|---------|---------|
| **Goal** | One-paragraph summary |
| **Behavioral specification** | Rules required for this phase (self-contained) |
| **Implementation** | Modules, interfaces, data flow |
| **Config / DB changes** | Schema or YAML changes |
| **Test plan** | Unit and integration tests |
| **Acceptance criteria** | Checkable "done" items |
| **Human-readable docs** | Links to domain docs for onboarding |
| **Open decisions** | Unresolved questions for this phase |

Read the phase doc top-to-bottom before starting. Update the matching domain docs when behavior changes.

---

## What "done" means

The project is complete when:

1. **Auto-discovery** (Phase 7) finds parents without manual seeding.
2. **Live execution** (Phase 8) places real CLOB orders behind the same adapter interface as paper.
3. **Backtesting** (Phase 6) replays history and compares PnL across config variants.
4. **Dashboard** (Phase 5) exposes alerts, positions, sessions, and false-positive labeling.
5. Full pipeline: discover → watch → detect → mirror (paper or live) → exit → analytics.

---

## Pre-flight fixes (Phase 0 → 1)

| Issue | Status | File |
|-------|--------|------|
| `aiosqlite` not declared | ✅ Done | `pyproject.toml` |
| No CLI entry point | ✅ Done | `pyproject.toml`, `cli.py` |
| Missing config keys from spec §14 | ✅ Done | `config/schema.py`, `default.yaml` |
| No RPC provider config | ✅ Done | `config/schema.py`, `default.yaml` |
