# Sessions & Analytics

**Source:** spec.md §12

---

## Sessions

Every paper/live run is tagged with a `sessionID`. Sessions track:

| Field | Description |
|-------|-------------|
| name | Human-readable label |
| mode | `observe` / `paper` / `live` |
| review_mode | `all` / `live_only` / `none` |
| config_snapshot | Immutable copy of config at session start |
| private | If true, excluded from global analytics |
| status | `running` / `completed` / `aborted` |

## Global analytics

- Users can include/exclude sessions from global stats post-hoc
- Dashboard must make inclusion toggles obvious

### Data persisted for analytics

- **Alerts:** event type, timestamps, parent, account, amounts, cluster score at event, rank
- **Accounts & clusters:** parent↔account edges, funding txs, cluster score history
- **Trades (theirs and ours):** full lifecycle per cluster×market: entry → net_adjustment(s) → exit → close reason → PnL. Each leg: source_sibling, net_before, net_after, our fill details, config snapshot at entry
- **Would-have-entered:** rules matched but review skipped
- **Hypothetical PnL** at various mirror caps
- **Latency distributions**
- **False positive labels** (`alerts.is_false_positive`)

Goal: answer "what min buy / TP / SL / discovery threshold actually worked?" without re-running history.
