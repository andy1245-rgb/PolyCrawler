# Implementation Phases

**Source:** [spec-full.md](spec-full.md) §16 | [phases/_index.md](../phases/_index.md)

---

Each phase has a **self-contained spec** in `docs/phases/` (behavior + implementation). Start at [phases/_index.md](../phases/_index.md).

---

## Phase overview

| Phase | Name | Status | Detailed doc |
|-------|------|--------|--------------|
| 0 | Bootstrap | ✅ Complete | [phase0-bootstrap.md](../phases/phase0-bootstrap.md) |
| 1 | Manual seed | ⬜ Not started | [phase1-manual-seed.md](../phases/phase1-manual-seed.md) |
| 2 | Parent watcher + scoring | ⬜ Not started | [phase2-parent-watcher.md](../phases/phase2-parent-watcher.md) |
| 3a | FSM + net calculator | ⬜ Not started | [phase3a-fsm-and-net.md](../phases/phase3a-fsm-and-net.md) |
| 3a | Trading rules | ⬜ Not started | [phase3a-trading-rules.md](../phases/phase3a-trading-rules.md) |
| 3b | Paper execution | ⬜ Not started | [phase3b-paper-execution.md](../phases/phase3b-paper-execution.md) |
| 4 | Reconciliation + RPC batching | ⬜ Not started | [phase4-reconciliation.md](../phases/phase4-reconciliation.md) |
| 5 | Dashboard API | ⬜ Not started | [phase5-dashboard-api.md](../phases/phase5-dashboard-api.md) |
| 6 | Backtesting | ⬜ Not started | [phase6-backtesting.md](../phases/phase6-backtesting.md) |
| 7 | Auto-discovery | ⬜ Not started | [phase7-auto-discovery.md](../phases/phase7-auto-discovery.md) |
| 8 | Live execution | ⬜ Not started | [phase8-live-execution.md](../phases/phase8-live-execution.md) |

## Critical path

**Phase 1 → 2 → 3a (both docs) → 3b → 4**

## Parallelization

- **Phase 2 scoring** — pure math; develop alongside ingestion adapter.
- **Phase 3a FSM + Phase 3a rules** — can develop in parallel.
- **Phase 5 (API)** — can start in parallel with Phase 4.
- **Phase 6 and Phase 7** — independent; both need Phase 3b.
