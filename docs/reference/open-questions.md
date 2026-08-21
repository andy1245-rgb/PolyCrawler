# Open Questions & Resolutions

**Source:** spec.md §20

---

| # | Question | Status | Notes |
|---|----------|--------|-------|
| 1 | Market tag / Layer D weighting | **Deferred** | Keep `entry.market_tags` as allow-list only until a weighting model is chosen. No score impact in v0.1. |
| 2 | Sibling opposing-side policy beyond CONFLICT alert | **Resolved** | `net_cluster_position` default (§7.7) |
| 3 | RPC provider budget | **Resolved (v0.1)** | Stay on **free-tier** public Polygon RPC with a soft rate limit (`rpc.budget_mode: free_tier`, `max_requests_per_second: 5`). Always log usage. Upgrade to paid + `capped` once the bot is profitable. |
| 4 | Telegram / external alerts | **TBD — needs decision** | `alerts.channels` already accepts `dashboard` / future `telegram` / `discord`. Wire-up blocked on bot token / webhook choice. |
| 5 | Cluster×market state machine | **Resolved** | §6 |
| 6 | Entry minBuyUsd / maxOdds on cluster net after poll batch | **Resolved** | §7.1 |
| 7 | hedgeFilterMode — net_only vs filter_before_net | **Resolved** | default net_only (§7.5) |
| 8 | followReentryAfterSell under net mirroring | **Resolved** | cluster net ~0 → non-zero (§7.6) |
| 9 | Per-account exit rows vs net-delta | **Resolved** | cluster-net only (§8.1) |

## What is blocked

- **#4 Telegram** does **not** block Phase 1–3b; dashboard channel is enough for paper trading.
- **#1 Tag weighting** does **not** block v0.1; allow-list filter is sufficient.
- **#3 RPC budget** no longer blocks Phase 2 — proceed with public RPC + usage logs; revisit caps when moving to a paid provider.

## Phase 2 questions intentionally deferred

These decisions are recorded for discussion when the relevant Phase 2 slice is reached:

1. **Polling/reorg policy:** block-range polling is preferred, but confirmation depth, re-scan behavior, chunk size, cursor persistence, and free-tier versus paid-tier tuning remain open.
2. **Profit reconstruction:** the scorer must use realized cashflow reconstruction rather than UI `cashPnl`; the exact Data API/chain inputs and reconstruction rules remain open.
3. **Event identity:** detection observes addresses before `Account` rows and UUIDs necessarily exist; the address-first event and persistence boundary remain open.
4. **Multicall details:** the abstraction boundary is agreed, but the exact private Multicall3 call encoding, failure semantics, batching limits, and retry behavior will be finalized during Track C.
