# Implementation Phases — Master Index

**Source:** spec.md §16 | docs/architecture.md §12

---

The project is built in 9 phases (0–8). Phase 0 is complete. Each phase below has a dedicated doc with full detail: goals, modules, interfaces, data flows, config changes, DB changes, test plans, and acceptance criteria.

---

## Phase overview

| Phase | Name | Status | Spec § | Key deliverable |
|-------|------|--------|--------|-----------------|
| [0](phase0-bootstrap.md) | Bootstrap | ✅ Complete | — | Repo skeleton, config, DB models, Alembic, FastAPI entry, test infra |
| [1](phase1-manual-seed.md) | Manual seed | ⬜ Not started | §16.1 | CLI to seed parent wallets + create cluster rows |
| [2](phase2-parent-watcher.md) | Parent watcher + scoring | ⬜ Not started | §16.2, §4 | IngestionAdapter, polling, event detection, scheduler, basic scorer |
| [3a](phase3a-engine-core.md) | Engine core | ⬜ Not started | §16.3 (pt 1) | FSM, net calc, entry/exit rules, hedge filter, reentry, processor |
| [3b](phase3b-paper-execution.md) | Paper execution | ⬜ Not started | §16.3 (pt 2) | ExecutionAdapter, orderbook walk, session manager, event logger |
| [4](phase4-reconciliation.md) | Reconciliation + RPC batching | ⬜ Not started | §16.4 | Balance multicall, reconciliation scanner, RPC log cleanup |
| [5](phase5-dashboard-api.md) | Dashboard API | ⬜ Not started | §16.5 | FastAPI routes for alerts, positions, sessions, config |
| [6](phase6-backtesting.md) | Backtesting | ⬜ Not started | §16.6 | Backtest runner, score validation, historical replay |
| [7](phase7-auto-discovery.md) | Auto-discovery | ⬜ Not started | §16.7 | Full discovery pipeline, auto-flagging with minClusterScore |
| [8](phase8-live-execution.md) | Live execution | ⬜ Not started | §16.8 | Live ExecutionAdapter, real CLOB order signing |

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
               ┌─────────▼──────────┐
               │     Phase 3a       │
               │   Engine Core      │ ◄── can start once RawEvent
               │   (FSM, rules)     │     shape is stable from Phase 2
               └─────────┬──────────┘
                         │
               ┌─────────▼──────────┐
               │     Phase 3b       │
               │ Paper Execution    │ ◄── needs engine core + orderbook fetch
               │ + Session/Logging  │
               └─────────┬──────────┘
                         │
               ┌─────────▼──────────┐
               │     Phase 4        │
               │ Reconciliation     │ ◄── hardens the paper engine
               │ + RPC Batching     │
               └─────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
   ┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐
   │  Phase 5    │ │ Phase 6   │ │  Phase 7   │
   │ Dashboard   │ │Backtesting│ │Auto-Discover│
   │ API         │ │           │ │            │
   └─────────────┘ └───────────┘ └─────┬──────┘
                                      │
                               ┌──────▼──────┐
                               │  Phase 8    │
                               │ Live Exec   │
                               └─────────────┘
```

### Parallelization opportunities

- **Phase 2 (scoring)** — the scorer is pure math; can be developed in parallel with the ingestion adapter within the same phase.
- **Phase 3a** can start as soon as Phase 2's `RawEvent` shape is stable, even before the polling adapter is fully wired — test against mock events.
- **Phase 5 (API)** can start in parallel with Phase 4 — the routes don't depend on reconciliation.
- **Phase 6 (backtesting)** and **Phase 7 (auto-discovery)** are independent of each other but both depend on Phase 3b being complete.

### Critical path

**Phase 1 → 2 → 3a → 3b → 4**

This sequence delivers a working paper-trading pipeline. Everything after that (dashboard, backtest, auto-discovery, live) layers on top.

---

## What "done" means

The project is complete when:

1. **Auto-discovery** (Phase 7) finds parents without manual seeding.
2. **Live execution** (Phase 8) can place real CLOB orders behind the same adapter interface used for paper.
3. **Backtesting** (Phase 6) can replay history and compare PnL across config variants.
4. **Dashboard** (Phase 5) exposes all alerts, positions, sessions, and the false-positive labeling button.
5. The full pipeline runs: discover → watch → detect → mirror (paper or live) → exit → analytics.

---

## How to use these docs

Each phase doc follows the same structure:

| Section | Content |
|---------|---------|
| **Goal** | One-paragraph summary of what this phase achieves |
| **Spec references** | Links to relevant spec/architecture sections |
| **Prerequisites** | What must be complete before starting |
| **Modules to build** | Every file to create, with purpose and interface |
| **Data flow** | Sequence of operations within the phase |
| **Config changes** | Any new config keys or schema modifications |
| **DB changes** | Any migration or schema additions |
| **Test plan** | Unit and integration tests to write |
| **Acceptance criteria** | Checkable items that define "phase complete" |
| **Open decisions** | Unresolved questions specific to this phase |

Read the phase doc top-to-bottom before starting implementation. Cross-reference the linked spec sections for full behavioral detail.

---

## Pre-flight fixes (before Phase 1)

These issues exist in the Phase 0 codebase and should be fixed before or during Phase 1:

| Issue | Fix | File |
|-------|-----|------|
| `aiosqlite` not declared as a dependency | ✅ Done — added to `[project.optional-dependencies] dev` | `pyproject.toml` |
| No CLI entry point defined | ✅ Done — `poly-crawler = "poly_crawler.cli:app"` in `[project.scripts]` | `pyproject.toml` |
| Missing config keys from spec §14 | ✅ Done — `max_slippage_pct`, `add_on_repeat_buy`, `notify_on_repeat_buy`, `tp_sl_suspend_mirror_until_flat` added to `ExitConfig` | `src/poly_crawler/config/schema.py`, `config/default.yaml` |
| No RPC provider config | ✅ Done — `rpc_url` added to config schema and YAML files | `config/schema.py`, `config/default.yaml`, `config/production.yaml` |
