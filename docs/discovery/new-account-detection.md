# Protocol 1 — New-Account Detection

**Source:** spec.md §5

---

Detects when a flagged parent funds a new Polymarket account (birth event).

### Detection flow

1. Poll on-chain for `FUND` transactions from known parent wallets
2. Identify the recipient Polymarket account
3. Classify account type (deposit wallet / safe / proxy / unknown)
4. Assign `watchStatus: active` to the new account
5. Link to parent in `accounts` table
6. Trigger alert: `alert_type: birth`

The account is now included in cluster polling — all future trades contribute to cluster net exposure.

Account lifecycle:

| Status | Meaning |
|--------|---------|
| `active` | Funded / trading; included in cluster polls |
| `expired` | No trades within `watch.accountExpireDays` of fund (configurable; optional) |

An expired account is **not** removed from the graph — a new trade reactivates polling.
