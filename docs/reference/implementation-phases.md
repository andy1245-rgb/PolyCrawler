# Implementation Phases

**Source:** spec.md §16 | docs/architecture.md §12

---

9-phase build order from bootstrap to live.

| Phase | What | Key deliverables |
|-------|------|------------------|
| **0** | Bootstrap | Repo, pyproject.toml, config schema, DB models, Alembic, folder structure |
| **1** | Discovery engine | Ingestion adapter, RPC client, Data API client, event detector, parent tracer |
| **2** | Clustering | Scorer (variants A/B/C), parent flagging, discovery loop |
| **3** | Paper engine | State machine, net calculator, entry/exit rules, hedge filter, re-entry, paper execution, orderbook walk, full poll cycle |
| **4** | Analytics | Session manager, event logger, aggregator |
| **5** | API | FastAPI app, alert/position/session/config routes |
| **6** | Dashboard | UI for alerts, positions, reviews, session management |
| **7** | Live execution | Live ExecutionAdapter, exchange connectivity, CLOB signing |
| **8** | Auto-discovery & backtesting | Automated parent discovery, backtest runner, scoring variant validation |

**Phase 0** is complete. The project is at the start of **Phase 1**.
