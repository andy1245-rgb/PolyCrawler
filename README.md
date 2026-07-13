# PolyCrawler

Detection and paper-trading pipeline for Polymarket accounts linked by on-chain funding (parent wallets → sibling accounts → early alerts before wins).

**Status:** v0.1.5 — Phase 0 (bootstrap) complete. Next: [Phase 1 — Manual seed](docs/phases/phase1-manual-seed.md).

## Documentation

| Doc | Purpose |
|-----|---------|
| [spec.md](./spec.md) | **Index** — start here |
| [docs/phases/_index.md](docs/phases/_index.md) | **Implementation specs** — one self-contained doc per phase |
| [docs/_index.md](docs/_index.md) | **Human-readable** — glossary, protocols, operations |
| [docs/reference/spec-full.md](docs/reference/spec-full.md) | Full archived specification |

## Summary

1. Trace **parent** funding wallets behind Polymarket accounts.
2. **Rank** clusters by a weighted score (profit-heavy; formula in spec).
3. **Watch** new accounts funded by flagged parents (zero trades required).
4. **Mirror** cluster net exposure in **paper mode** first; live optional later.
5. **Analytics** with sessions, global rollups, and rich event logging.

## License

TBD
