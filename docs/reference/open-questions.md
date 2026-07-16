# Open Questions & Resolutions

**Source:** spec.md §20

---

| # | Question | Status | Notes |
|---|----------|--------|-------|
| 1 | Market tag / Layer D weighting | **Deferred** | Keep `entry.market_tags` as allow-list only until a weighting model is chosen. No score impact in v0.1. |
| 2 | Sibling opposing-side policy beyond CONFLICT alert | **Resolved** | `net_cluster_position` default (§7.7) |
| 3 | RPC provider budget | **TBD — needs decision** | Config has `rpc_url` + `rpc_logs` table. Still need monthly CU/request budget and throttle policy before Phase 2 polling. |
| 4 | Telegram / external alerts | **TBD — needs decision** | `alerts.channels` already accepts `dashboard` / future `telegram` / `discord`. Wire-up blocked on bot token / webhook choice. |
| 5 | Cluster×market state machine | **Resolved** | §6 |
| 6 | Entry minBuyUsd / maxOdds on cluster net after poll batch | **Resolved** | §7.1 |
| 7 | hedgeFilterMode — net_only vs filter_before_net | **Resolved** | default net_only (§7.5) |
| 8 | followReentryAfterSell under net mirroring | **Resolved** | cluster net ~0 → non-zero (§7.6) |
| 9 | Per-account exit rows vs net-delta | **Resolved** | cluster-net only (§8.1) |

## What is blocked

- **#3 RPC budget** blocks safe Phase 2 parent-watcher polling (rate limits / cost).
- **#4 Telegram** does **not** block Phase 1–3b; dashboard channel is enough for paper trading.
- **#1 Tag weighting** does **not** block v0.1; allow-list filter is sufficient.
