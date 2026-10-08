# Implementation Phases

**Source:** spec.md §16 | docs/architecture.md §12

---

The project is built in 9 phases (0–8). Each phase has a dedicated doc in `docs/phases/` with full detail: goals, modules, interfaces, data flows, config changes, DB changes, test plans, and acceptance criteria.

**Full phase documentation:** [docs/phases/_index.md](../phases/_index.md)

---

## Phase overview

| Phase | Name | Status | Detailed doc |
|-------|------|--------|--------------|
| 0 | Bootstrap | ✅ Complete | [phase0-bootstrap.md](../phases/phase0-bootstrap.md) |
| 1 | Manual seed | ⬜ Not started | [phase1-manual-seed.md](../phases/phase1-manual-seed.md) |
| 2 | Parent watcher + scoring | ⬜ Not started | [phase2-parent-watcher.md](../phases/phase2-parent-watcher.md) |
| 3a | Engine core | ⬜ Not started | [phase3a-engine-core.md](../phases/phase3a-engine-core.md) |
| 3b | Paper execution | ⬜ Not started | [phase3b-paper-execution.md](../phases/phase3b-paper-execution.md) |
| 4 | Reconciliation + RPC batching | ⬜ Not started | [phase4-reconciliation.md](../phases/phase4-reconciliation.md) |
| 5 | Dashboard API | ⬜ Not started | [phase5-dashboard-api.md](../phases/phase5-dashboard-api.md) |
| 6 | Backtesting | ⬜ Not started | [phase6-backtesting.md](../phases/phase6-backtesting.md) |
| 7 | Auto-discovery | ⬜ Not started | [phase7-auto-discovery.md](../phases/phase7-auto-discovery.md) |
| 8 | Live execution | ⬜ Not started | [phase8-live-execution.md](../phases/phase8-live-execution.md) |

## Critical path

**Phase 1 → 2 → 3a → 3b → 4**

This sequence delivers a working paper-trading pipeline. Everything after that (dashboard, backtest, auto-discovery, live) layers on top.

## Parallelization

- **Phase 2 scoring** — pure math, can be developed alongside the ingestion adapter within the same phase.
- **Phase 3a** can start once Phase 2's `RawEvent` shape is stable — test against mock events.
- **Phase 5 (API)** can start in parallel with Phase 4 — routes don't depend on reconciliation.
- **Phase 6 (backtesting)** and **Phase 7 (auto-discovery)** are independent but both depend on Phase 3b.
