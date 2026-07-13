# PolyCrawler — Spec Index (v0.1.5)

> **Development entry point.** Each implementation phase has a self-contained spec in [docs/phases/](docs/phases/_index.md). Domain concepts live under [docs/_index.md](docs/_index.md).

---

## What this project does

When money from a parent wallet we already care about lands in a new Polymarket account, watch the cluster; when the cluster has net exposure in a market, mirror it (paper or live); when cluster net goes flat, hedged, or resolved, exit; log everything for accuracy testing before risking capital.

**Status:** Phase 0 (bootstrap) complete. Next: [Phase 1 — Manual seed](docs/phases/phase1-manual-seed.md).

---

## Where to read what

| You want… | Read… |
|-----------|--------|
| **Implement the next phase** | [docs/phases/_index.md](docs/phases/_index.md) → open that phase doc |
| **Understand a concept** (glossary, protocols, alerts) | [docs/_index.md](docs/_index.md) — human-readable domain docs |
| **Architecture & interfaces** | [docs/architecture.md](docs/architecture.md) |
| **Config keys, DB schema, API routes** | [docs/reference/](docs/reference/configuration.md) |

---

## Implementation phases

| Phase | Doc | Status | Deliverable |
|-------|-----|--------|-------------|
| 0 | [phase0-bootstrap.md](docs/phases/phase0-bootstrap.md) | ✅ Complete | Repo skeleton, config, DB, tests |
| 1 | [phase1-manual-seed.md](docs/phases/phase1-manual-seed.md) | ⬜ Not started | CLI to seed parent wallets |
| 2 | [phase2-parent-watcher.md](docs/phases/phase2-parent-watcher.md) | ⬜ Not started | FUND/BIRTH ingestion + scoring |
| 3a | [phase3a-fsm-and-net.md](docs/phases/phase3a-fsm-and-net.md) | ⬜ Not started | Position FSM, net calculator, processor |
| 3a | [phase3a-trading-rules.md](docs/phases/phase3a-trading-rules.md) | ⬜ Not started | Entry, exit, hedge, re-entry, review |
| 3b | [phase3b-paper-execution.md](docs/phases/phase3b-paper-execution.md) | ⬜ Not started | Paper fills, sessions, event logging |
| 4 | [phase4-reconciliation.md](docs/phases/phase4-reconciliation.md) | ⬜ Not started | Balance reconciliation + RPC batching |
| 5 | [phase5-dashboard-api.md](docs/phases/phase5-dashboard-api.md) | ⬜ Not started | FastAPI dashboard routes |
| 6 | [phase6-backtesting.md](docs/phases/phase6-backtesting.md) | ⬜ Not started | Historical replay + score validation |
| 7 | [phase7-auto-discovery.md](docs/phases/phase7-auto-discovery.md) | ⬜ Not started | Auto-flag parents by cluster score |
| 8 | [phase8-live-execution.md](docs/phases/phase8-live-execution.md) | ⬜ Not started | Live CLOB execution adapter |

**Critical path:** 1 → 2 → 3a (both) → 3b → 4. Phases 5, 6, and 7 can run in parallel after 3b. Phase 8 is last.

---

## Phase doc structure

Every phase doc follows the same layout:

1. **Goal** — what this phase achieves
2. **Behavioral specification** — rules needed to implement (self-contained in the phase doc)
3. **Implementation** — modules, data flow, config/DB changes
4. **Test plan & acceptance criteria** — how to verify done
5. **Human-readable docs** — links to domain docs for onboarding

---

## Document history

See [docs/architecture/document-history.md](docs/architecture/document-history.md).

| Version | Changes |
|---------|---------|
| v0.1.5 | Spec split into phase docs; archive deleted after migration; §6.2 formatting fixed |
| v0.1.5 | `CLOSED` clarified; `tp_sl_mirror_suspended_until_flat` rename |
| v0.1.4 | Full cluster×market state machine; hedge modes |
| v0.1.0 | Initial protocols and bootstrap |
