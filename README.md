# PolyCrawler

Detection and paper-trading pipeline for Polymarket accounts linked by on-chain funding (parent wallets → sibling accounts → early alerts before wins).

**Status:** v0.1.0 — specification only. Implementation not started.

## Spec

See [spec.md](./spec.md) for product behavior, protocols, configuration defaults, and implementation phases.

## Summary

1. Trace **parent** funding wallets behind Polymarket accounts.
2. **Rank** clusters by a weighted score (profit-heavy; formula candidate in spec).
3. **Watch** new accounts funded by flagged parents (zero trades required).
4. **Mirror** target buys/sells in **paper mode** first; live optional later.
5. **Analytics** with sessions, global rollups, and rich event logging.

## License

TBD
