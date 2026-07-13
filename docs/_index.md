# PolyCrawler — Documentation Index

Documentation has two layers:

1. **Implementation phases** ([phases/_index.md](phases/_index.md)) — self-contained specs for building each phase. **Use these when coding.**
2. **Domain docs** (below) — human-readable reference for understanding concepts. **Use these when onboarding.**

**Spec index (repo root):** [../spec.md](../spec.md)

---

## [Phases](phases/) — implementation specs

| Doc | Phase | Status |
|-----|-------|--------|
| [_index.md](phases/_index.md) | Master index | — |
| [phase0-bootstrap.md](phases/phase0-bootstrap.md) | 0 Bootstrap | ✅ |
| [phase1-manual-seed.md](phases/phase1-manual-seed.md) | 1 Manual seed | ✅ |
| [phase2-parent-watcher.md](phases/phase2-parent-watcher.md) | 2 Parent watcher | ⬜ |
| [phase3a-fsm-and-net.md](phases/phase3a-fsm-and-net.md) | 3a FSM + net | ⬜ |
| [phase3a-trading-rules.md](phases/phase3a-trading-rules.md) | 3a Trading rules | ⬜ |
| [phase3b-paper-execution.md](phases/phase3b-paper-execution.md) | 3b Paper execution | ⬜ |
| [phase4-reconciliation.md](phases/phase4-reconciliation.md) | 4 Reconciliation | ⬜ |
| [phase5-dashboard-api.md](phases/phase5-dashboard-api.md) | 5 Dashboard API | ⬜ |
| [phase6-backtesting.md](phases/phase6-backtesting.md) | 6 Backtesting | ⬜ |
| [phase7-auto-discovery.md](phases/phase7-auto-discovery.md) | 7 Auto-discovery | ⬜ |
| [phase8-live-execution.md](phases/phase8-live-execution.md) | 8 Live execution | ⬜ |

---

## [Overview](overview/)

| File | Covers | Implementation phase |
|------|--------|---------------------|
| [purpose.md](overview/purpose.md) | Goals, product sentence, non-goals | All |
| [glossary.md](overview/glossary.md) | Terms (parent, sibling, cluster, net exposure) | All |
| [account-types.md](overview/account-types.md) | Deposit wallet, Safe, proxy | [Phase 2](phases/phase2-parent-watcher.md) |

## [Discovery](discovery/)

| File | Covers | Implementation phase |
|------|--------|---------------------|
| [clustering.md](discovery/clustering.md) | Cluster scoring, weights, flagging | [Phase 2](phases/phase2-parent-watcher.md), [Phase 7](phases/phase7-auto-discovery.md) |
| [new-account-detection.md](discovery/new-account-detection.md) | Protocol 1 — FUND/BIRTH | [Phase 2](phases/phase2-parent-watcher.md) |

## [Protocols](protocols/)

| File | Covers | Implementation phase |
|------|--------|---------------------|
| [position-state-machine.md](protocols/position-state-machine.md) | Protocol 2 — FSM | [Phase 3a FSM](phases/phase3a-fsm-and-net.md) |
| [entry-rules.md](protocols/entry-rules.md) | Protocol 3 — entry | [Phase 3a Rules](phases/phase3a-trading-rules.md) |
| [exit-rules.md](protocols/exit-rules.md) | Protocol 4 — exit | [Phase 3a Rules](phases/phase3a-trading-rules.md), [Phase 4](phases/phase4-reconciliation.md) |
| [review-and-autonomy.md](protocols/review-and-autonomy.md) | Protocol 5 — review gates | [Phase 3a Rules](phases/phase3a-trading-rules.md) |

## [Execution](execution/)

| File | Covers | Implementation phase |
|------|--------|---------------------|
| [modes.md](execution/modes.md) | Observe / paper / live | [Phase 3b](phases/phase3b-paper-execution.md), [Phase 8](phases/phase8-live-execution.md) |
| [paper-fill-model.md](execution/paper-fill-model.md) | Orderbook walk, VWAP | [Phase 3b](phases/phase3b-paper-execution.md) |

## [Operations](operations/)

| File | Covers | Implementation phase |
|------|--------|---------------------|
| [alerts.md](operations/alerts.md) | Alert types, false-positive labeling | [Phase 5](phases/phase5-dashboard-api.md) |
| [sessions-and-analytics.md](operations/sessions-and-analytics.md) | Sessions, global analytics | [Phase 3b](phases/phase3b-paper-execution.md), [Phase 5](phases/phase5-dashboard-api.md) |
| [end-to-end-flow.md](operations/end-to-end-flow.md) | Full pipeline diagram | All phases |

## [Reference](reference/)

| File | Covers |
|------|--------|
| [configuration.md](reference/configuration.md) | All config keys |
| [database-schema.md](reference/database-schema.md) | All 11 tables |
| [api-routes.md](reference/api-routes.md) | FastAPI endpoints |
| [tech-stack.md](reference/tech-stack.md) | Python deps, tooling |
| [implementation-phases.md](reference/implementation-phases.md) | Phase summary (links to phases/) |
| [data-retention.md](reference/data-retention.md) | Log retention |
| [testing-strategy.md](reference/testing-strategy.md) | Test inventory |
| [scripts-and-tooling.md](reference/scripts-and-tooling.md) | Makefile, dev scripts |
| [phase0-complete.md](reference/phase0-complete.md) | Phase 0 deliverables detail |
| [open-questions.md](reference/open-questions.md) | Open design questions |

## [Architecture](architecture/)

| File | Covers |
|------|--------|
| [architecture.md](architecture.md) | Technical architecture |
| [component-interfaces.md](architecture/component-interfaces.md) | Adapter interfaces |
| [document-history.md](architecture/document-history.md) | Changelog |

---

## Maintaining docs

When behavior changes during a phase:

1. Update the **phase doc** first (source of truth for implementation).
2. Update the matching **domain doc** if humans need the concept explained.

### Doc format

```markdown
# Title

**Source:** [phaseN-….md](phases/phaseN-….md) (behavioral spec)
**Related:** [architecture.md](architecture.md) §N

---
```

- Phase docs: Goal → Behavioral specification → Implementation → Tests → Acceptance
- Domain docs: concise explanation + link to phase doc
- Keep files focused — split don't bloat

### Verification checklist

1. Phase doc updated with behavioral + implementation sections
2. Domain doc updated if concept changed
3. Listed in this index
4. Internal links valid
5. No references to deleted files
