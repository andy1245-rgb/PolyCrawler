# Protocol 4 — Exit Rules

**Source:** [phase3a-trading-rules.md](../phases/phase3a-trading-rules.md), [phase4-reconciliation.md](../phases/phase4-reconciliation.md)
**Related:** [architecture.md](../architecture.md) §7

---

Exits are evaluated on each poll cycle for positions in `IN_POSITION` state.

> **Polling note:** Exit detection uses configurable poll intervals, not real-time websockets. Missed events between polls are corrected by position reconciliation (Phase 4).

### Exit priority (first match wins)

1. Cluster net flat / hedged / redeemed (incl. reconciliation)
2. Take profit hit on mirrored position (default: disabled)
3. Stop loss hit on mirrored position (default: disabled)
4. Max hold time exceeded (default: disabled)
5. Market resolved per Data API (default: on)

### Configuration

```yaml
exit:
  poll_interval_sec: 60
  take_profit_enabled: false
  take_profit_pct: 0.50       # 50% gain
  stop_loss_enabled: false
  stop_loss_pct: 0.25         # 25% loss
  max_hold_hours: null        # off
  close_on_resolution: true
  add_on_repeat_buy: false
  notify_on_repeat_buy: true  # dashboard notice when net unchanged but sibling rebuys
```

**Default (v0.1):** hold until cluster net is flat/hedged, siblings redeem, reconciliation catches up, or the market resolves. No TP/SL unless explicitly enabled.

When `entry.followReentryAfterSell` is on, it overrides `exit.addOnRepeatBuy` being false for that re-entry path.

### TP/SL suspension

When a position closes due to TP or SL, set `tp_sl_mirror_suspended_until_flat` on the cluster position. While true: do not re-enter or resume mirroring until cluster net ~0 (then clear flag). Other close reasons (hedge, redeem, resolution) do **not** set this flag.

### Close reasons (canonical)

| Reason | When |
|--------|------|
| `cluster_hedged` | Cluster net → ~0 (within `min_net_usd`), including opposing siblings / redeem |
| `reconciled` | Balance poll corrected net → ~0 after missed events |
| `tp_hit` | Take profit target reached |
| `sl_hit` | Stop loss triggered |
| `max_hold` | Time limit exceeded |
| `resolved` | Market resolved per Data API |
| `net_adjustment` | (not a close) — mirror delta while staying `IN_POSITION` |
