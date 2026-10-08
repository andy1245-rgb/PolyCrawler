# Glossary

**Source:** spec.md §2

---

| Term | Meaning |
|------|---------|
| **Parent wallet** | On-chain address that funds Polymarket accounts (EOA, CEX withdrawal path, etc.). Primary identity anchor for clustering. |
| **Polymarket account** | A tradable address on Polymarket. Tracked methods: deposit wallet, Safe, or proxy. |
| **Sibling** | Another Polymarket account funded by the same parent wallet. |
| **Cluster** | Parent + all linked Polymarket accounts + their derived scores. |
| **Cluster score** | Weighted quality of a cluster. Used **only** for discovery, flagging, and alert **ranking** — **not** for trade entry. |
| **Flagged parent** | Parent that met discovery criteria and is on the watchlist. |
| **Paper trade** | Simulated fill; no wallet or capital required. |
| **Session** | A bounded run of paper/live activity with its own stats. |
| **Global analytics** | Aggregated stats across selected sessions (configurable inclusion). |
| **Sell** | Closing/reducing a position on the order book before resolution. |
| **Redeem** | Cashing out winning shares after a market resolved (not a normal sell). |
| **Merge / split** | On-chain ops converting USDC ↔ outcome token pairs. v0.1: log only, no auto-trade. |
| **Position reconciliation** | If sibling share balances drop but we missed sell events, close or adjust our mirrored position to match cluster net. |
| **Net exposure** | Per market, per cluster: (sum of Yes shares across siblings) − (sum of No shares across siblings). Positive = net Yes; negative = net No. |
| **Net cluster mirroring** | Mirror the cluster's net exposure (not a single account). Position size = net × mirrorPct, capped by mirrorCapUsd; adjust on each net change. |
| **CONFLICT alert** | Two or more siblings hold opposing sides of the same market (both above dust). Always logged when `conflict.always_alert` is true. |
| **CONFLICT_RESOLVED alert** | Opposing sibling overlap ended — net within dust or one side flat. |
| **Follow re-entry** | Cluster net was ~flat, then becomes non-zero again within `reentryWindowMinutes` — mirror as new entry if rules pass. |
