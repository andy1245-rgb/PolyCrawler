# Protocol 4 — Exit Rules

**Source:** spec.md §8 | docs/architecture.md §7

---

Exits are evaluated on each poll cycle for positions in `IN_POSITION` state.

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
```

### TP/SL suspension

When a position closes due to TP or SL, `tp_sl_suspended` is set on the cluster position. The system won't re-enter on the same side until cluster net goes flat first — prevents whipsaw re-entries.

### Close reasons

- `net_flat` — cluster net returned to ~0
- `hedged` — opposing siblings cancelled net
- `redeemed` — winning shares cashed out after resolution
- `reconciliation` — balance poll disagreed with event tracking
- `tp_hit` — take profit target reached
- `sl_hit` — stop loss triggered
- `max_hold` — time limit exceeded
- `resolved` — market resolved
