# End-to-End Flow

**Source:** [phases/_index.md](../phases/_index.md) critical path

---

The v0.1 pipeline from seed to analytics:

```
MANUAL parent seed (5–10 wallets from research)
       ↓
PARENT watcher → FUND/BIRTH on seeded parents only
       ↓
RANK by clusterScore → WATCH cluster (scanners on all siblings)
       ↓
Sibling trade(s) → cluster net ≠ 0, entry rules pass → SIGNAL → [review?] → IN_POSITION (paper)
       ↓
FAST post-entry polls → normal polls → net deltas / hedge flat / redeem / reconcile / resolution
       ↓
CLOSED → analytics (session + optional global)
       ↓
(later) AUTO-DISCOVERY + backtests to tune cluster score
```
