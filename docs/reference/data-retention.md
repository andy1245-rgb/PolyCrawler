# Data Retention

**Source:** [phase4-reconciliation.md](../phases/phase4-reconciliation.md)

---

| Data | Retention | Config |
|------|-----------|--------|
| Raw trade / poll logs | 90 days | `retention.raw_trades_days` |
| Analytics aggregates, paper PnL, session summaries | Indefinite | `retention.analytics_indefinite` |
| RPC usage logs | 90 days | (same as raw trades) |
