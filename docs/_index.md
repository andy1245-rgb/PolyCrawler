# PolyCrawler — Documentation Index

Documentation is organized by domain, mirroring the structure of `spec.md` (§ sections) and `docs/architecture.md`.

---

## [Overview](overview/)
| File | Covers | Source |
|------|--------|--------|
| [purpose.md](overview/purpose.md) | Project goals, core product sentence, non-goals | spec §1 |
| [glossary.md](overview/glossary.md) | All defined terms (parent, sibling, cluster, net exposure, etc.) | spec §2 |
| [account-types.md](overview/account-types.md) | Deposit wallet, Safe, proxy — detection timing | spec §3 |

## [Discovery](discovery/)
| File | Covers | Source |
|------|--------|--------|
| [clustering.md](discovery/clustering.md) | Cluster scoring variants, weights, parent tracing | spec §4, arch §9 |
| [new-account-detection.md](discovery/new-account-detection.md) | Protocol 1 — birth/fund detection, polling | spec §5 |

## [Protocols](protocols/)
| File | Covers | Source |
|------|--------|--------|
| [position-state-machine.md](protocols/position-state-machine.md) | Protocol 2 — WATCHING → SIGNAL → IN_POSITION → CLOSED | spec §6, arch §5 |
| [entry-rules.md](protocols/entry-rules.md) | Protocol 3 — entry conditions, max odds, mirror sizing, hedges, re-entry | spec §7, arch §6 |
| [exit-rules.md](protocols/exit-rules.md) | Protocol 4 — exit conditions, TP/SL, max hold, resolution | spec §8, arch §7 |
| [review-and-autonomy.md](protocols/review-and-autonomy.md) | Protocol 5 — SIGNAL review gates per mode | spec §9 |

## [Execution](execution/)
| File | Covers | Source |
|------|--------|--------|
| [modes.md](execution/modes.md) | Observe / paper / live — shared engine, swappable adapter | spec §10 |
| [paper-fill-model.md](execution/paper-fill-model.md) | Orderbook walk, VWAP, slippage, pessimistic adjustments | spec §10.1, arch §8 |

## [Operations](operations/)
| File | Covers | Source |
|------|--------|--------|
| [alerts.md](operations/alerts.md) | Alert types, channels, false-positive labeling | spec §11 |
| [sessions-and-analytics.md](operations/sessions-and-analytics.md) | Session lifecycle, global analytics, data to persist | spec §12 |
| [end-to-end-flow.md](operations/end-to-end-flow.md) | Full pipeline from parent seed to analytics | spec §13 |

## [Reference](reference/)
| File | Covers | Source |
|------|--------|--------|
| [configuration.md](reference/configuration.md) | All config keys, defaults, env var mapping | spec §14, arch §3 |
| [database-schema.md](reference/database-schema.md) | All 12 tables, columns, relationships | spec §19, arch §2 |
| [api-routes.md](reference/api-routes.md) | FastAPI endpoint definitions | arch §10 |
| [tech-stack.md](reference/tech-stack.md) | Python deps, async stack, tooling | spec §15 |
| [implementation-phases.md](reference/implementation-phases.md) | Build order: 9 phases from bootstrap to live | spec §16, arch §12 |
| [data-retention.md](reference/data-retention.md) | Trade logs, analytics, RPC log retention | spec §18 |
| [testing-strategy.md](reference/testing-strategy.md) | Unit + integration test inventory, fixtures | arch §11 |
| [open-questions.md](reference/open-questions.md) | Open design questions and resolutions | spec §20 |

## [Architecture](architecture/)
| File | Covers | Source |
|------|--------|--------|
| [project-structure.md](architecture/project-structure.md) | Directory tree, module responsibilities | arch §1 |
| [component-interfaces.md](architecture/component-interfaces.md) | IngestionAdapter, ExecutionAdapter, Engine | arch §4 |
| [document-history.md](architecture/document-history.md) | Spec version changelog | spec §21 |
