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
| [scripts-and-tooling.md](reference/scripts-and-tooling.md) | Makefile, dev.ps1, validate_schema, uvicorn, alembic usage | Phase 0 |
| [phase0-complete.md](reference/phase0-complete.md) | Phase 0 bootstrap deliverables — entry point, migration, conftest, scripts | §16 / Phase 0 |
| [open-questions.md](reference/open-questions.md) | Open design questions and resolutions | spec §20 |

## [Architecture](architecture/)
| File | Covers | Source |
|------|--------|--------|
| [architecture.md](architecture.md) | Full technical architecture — design decisions, schema, interfaces, FSM, build order | arch (all) |
| [project-structure.md](architecture/project-structure.md) | Directory tree, module responsibilities | arch §1 |
| [component-interfaces.md](architecture/component-interfaces.md) | IngestionAdapter, ExecutionAdapter, Engine | arch §4 |
| [document-history.md](architecture/document-history.md) | Spec version changelog | spec §21 |

## [Phases](phases/)
| File | Covers | Source |
|------|--------|--------|
| [_index.md](phases/_index.md) | Master phase index, dependency graph, critical path | spec §16, arch §12 |
| [phase0-bootstrap.md](phases/phase0-bootstrap.md) | ✅ Complete — repo skeleton, config, DB, Alembic, test infra | Phase 0 |
| [phase1-manual-seed.md](phases/phase1-manual-seed.md) | CLI to seed parent wallets + create cluster rows | spec §16.1 |
| [phase2-parent-watcher.md](phases/phase2-parent-watcher.md) | Ingestion adapter, polling, event detection, scheduler, scorer | spec §16.2, §4, §5 |
| [phase3a-engine-core.md](phases/phase3a-engine-core.md) | FSM, net calc, entry/exit rules, hedge filter, reentry, processor | spec §16.3, §6, §7, §8 |
| [phase3b-paper-execution.md](phases/phase3b-paper-execution.md) | ExecutionAdapter, orderbook walk, session manager, event logger | spec §16.3, §10, §12 |
| [phase4-reconciliation.md](phases/phase4-reconciliation.md) | Balance multicall, reconciliation scanner, RPC batching | spec §16.4, §8.2 |
| [phase5-dashboard-api.md](phases/phase5-dashboard-api.md) | FastAPI routes for alerts, positions, sessions, config | spec §16.5, §11, §12 |
| [phase6-backtesting.md](phases/phase6-backtesting.md) | Backtest runner, score validation, historical replay | spec §16.6, §17 |
| [phase7-auto-discovery.md](phases/phase7-auto-discovery.md) | Full discovery pipeline, auto-flagging with minClusterScore | spec §16.7, §4.3 |
| [phase8-live-execution.md](phases/phase8-live-execution.md) | Live ExecutionAdapter, real CLOB order signing | spec §16.8, §10 |

---

## AI Agent — Documentation Conventions

This section tells future AI agents (and human contributors) how to maintain the documentation.

### Where to put new docs

| If you're documenting… | Put it in… |
|------------------------|-----------|
| A new module, class, or public function | `docs/reference/` — one doc per module |
| A protocol or rule | `docs/protocols/` — one doc per protocol |
| A workflow, alert type, or operational concept | `docs/operations/` |
| An architecture decision, interface, or structure | `docs/architecture/` |
| An overview concept (glossary, purpose, account types) | `docs/overview/` |
| Discovery or clustering logic | `docs/discovery/` |
| Execution modes or fill models | `docs/execution/` |

### When to add a new doc file

Create a new `.md` file when:

- You implement a module that was previously an empty stub (e.g., adding `engine/processor.py` → add to `docs/reference/`)
- You add a new protocol, config key, API endpoint, or alert type
- You change a documented interface signature

### Updating existing docs

When you modify existing code, update the corresponding doc in the same commit:

| Code change | Doc to update |
|-------------|---------------|
| New config key | `docs/reference/configuration.md` |
| New DB column or table | `docs/reference/database-schema.md` |
| New API route | `docs/reference/api-routes.md` |
| New module or file | `docs/architecture/project-structure.md` |
| New test or fixture | `docs/reference/testing-strategy.md` |
| New script or build target | `docs/reference/scripts-and-tooling.md` |
| Modified interface | `docs/architecture/component-interfaces.md` |

### Doc format conventions

Every doc file must follow this structure:

```markdown
# Title

**Source:** spec.md §N | docs/architecture.md §N

---

Body text. Use tables for structured data, code blocks for examples,
and bullet lists for unordered items.
```

- Always include a `**Source:**` line linking back to the spec or architecture doc
- Use `---` as a section separator below the title/source block
- Prefer tables, code blocks, and bullet lists over prose paragraphs
- Keep files focused on one topic — split don't bloat

### Linking between docs

- Use relative paths from the `docs/` root: `[configuration.md](reference/configuration.md)`
- Link to source sections: `**Source:** [implementation-phases.md §Phase 0](reference/implementation-phases.md)`
- Cross-reference spec sections: `spec §14`, `arch §3`

### Verification

After adding or updating docs, verify:

1. The file is listed in this index (`docs/_index.md`)
2. All internal links are valid relative paths
3. The `**Source:**` line accurately references the spec or architecture document
4. Code examples are tested (or at minimum, syntactically valid)
