# Data Retention

**Source:** spec.md §18

---

| Data | Retention | Config |
|------|-----------|--------|
| Raw trade / poll logs | 90 days | `retention.raw_trades_days` |
| Analytics aggregates, paper PnL, session summaries | Indefinite | `retention.analytics_indefinite` |
| RPC usage logs | 90 days | (same as raw trades) |
