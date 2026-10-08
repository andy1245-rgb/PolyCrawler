# Purpose

**Source:** spec.md §1

---

PolyCrawler traces parent funding wallets behind Polymarket accounts, ranks clusters by score, watches new siblings, mirrors cluster net exposure in paper mode, and logs everything for analytics.

### Core product sentence

> When money from a parent we already care about lands in a new Polymarket account, watch the cluster; when the cluster has net exposure in a market, mirror it (paper or live); when cluster net goes flat, hedged, or resolved, we exit; log everything for accuracy testing before risking capital.

### Goals

1. Find Polymarket accounts likely connected to the same real-world operator (parent funding wallet + sibling accounts)
2. Watch new accounts funded by already-flagged parents before they win (ideally on first deposit)
3. Mirror cluster net exposure in paper mode first, then optionally live
4. Record rich analytics so entry/exit rules, scoring weights, and thresholds can be tuned from real data

### Non-goals (v0.1)

- Perfect insider conviction
- Legal classification
- Beating Chainalysis/PolyInsider on generic fresh-wallet alerts
