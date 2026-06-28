# Configuration Reference

**Source:** spec.md §14 | docs/architecture.md §3

---

Full configuration schema with defaults. All keys can be overridden via environment variables with the `POLY_` prefix and `__` delimiter for nested keys.

## Discovery

```yaml
discovery:
  min_sibling_count: 2
  min_cluster_score: null        # overrides min_sibling_count when set
  funding_hops: 3
  profit_formula: sqrt           # sqrt | log | piecewise
  subtract_losses: false
  weights:
    profit: 2.0
    efficiency: 15.0
    win_rate: 5.0
  efficiency_cap: 10.0
  min_exit_count_for_win_rate: 1
```

## Entry

```yaml
entry:
  min_buy_usd: 500.0
  market_tags: []                # empty = all markets qualify
  max_odds_enabled: true
  max_odds: 0.5
  mirror_pct: 1.0
  mirror_cap_usd: null
  post_entry_poll_interval_sec: 10
  post_entry_poll_count: 6
  hedge_filter_mode: net_only    # net_only | filter_before_net
  ignore_hedge_trades: true
  hedge_dominant_threshold: 2.0
  follow_reentry_after_sell: true
  reentry_window_minutes: 5
```

## Exit

```yaml
exit:
  poll_interval_sec: 60
  take_profit_enabled: false
  take_profit_pct: 0.50
  stop_loss_enabled: false
  stop_loss_pct: 0.25
  max_hold_hours: null
  close_on_resolution: true
```

## Review / Execution / Paper

```yaml
review:
  mode: live_only                # all | live_only | none

execution:
  mode: paper                    # observe | paper | live

paper:
  fill_model: orderbook_walk_next_poll
  pessimistic_slippage_pct: 0.0
```

## Conflict

```yaml
conflict:
  policy: net_cluster_position   # alert_only | net_cluster_position
  min_net_usd: 100.0
  dust_shares: 0.001
  always_alert: true
```

## Position / Watch

```yaml
position:
  signal_expire_minutes: null
  market_watch_expire_days: null

watch:
  account_expire_days: null
```

## Alerts / Retention / Sessions

```yaml
alerts:
  channels:
    - dashboard

retention:
  raw_trades_days: 90
  analytics_indefinite: true

sessions:
  private_default: false
```

## Config load chain

1. `config/default.yaml` — baseline (committed to git, always loaded)
2. `config/production.yaml` — optional file-level override template.
   - **Not loaded automatically.** Apply it at runtime with `POLY_CONFIG=config/production.yaml`.
   - See [phase0-complete.md §2](./phase0-complete.md#2-production-configuration-overrides) for the override template contents.
3. File referenced by the `POLY_CONFIG` environment variable (any path, any name)
4. Environment variables prefixed with `POLY_` — highest priority
   - Nested keys use `__`: e.g. `POLY_ENTRY__MAX_ODDS=0.3`

Usage:

```bash
# Apply production overrides
POLY_CONFIG=config/production.yaml uvicorn poly_crawler.main:app

# Environment variables override everything
POLY_ENTRY__MIN_BUY_USD=1000 POLY_CONFIG=config/production.yaml uvicorn poly_crawler.main:app
```
