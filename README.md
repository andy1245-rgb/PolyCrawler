# PolyCrawler

Detection and paper-trading pipeline for Polymarket accounts linked by on-chain funding (parent wallets → sibling accounts → early alerts before wins).

**Status:** v0.1.5 — Phase 0 (bootstrap) complete. Next: [Phase 1 — Manual seed](docs/phases/phase1-manual-seed.md).

## Documentation

Two-layer model — no archived monolith:

| Doc | Purpose |
|-----|---------|
| [spec.md](./spec.md) | **Index** — start here |
| [docs/phases/_index.md](docs/phases/_index.md) | **Implementation specs** — one self-contained doc per phase |
| [docs/_index.md](docs/_index.md) | **Human-readable** — glossary, protocols, operations |
| [docs/architecture.md](docs/architecture.md) | Technical architecture |

### How to start developing

```bash
pip install -e ".[dev]"
# Read the phase doc for the work you are doing, then implement + test.
# Phase 1: docs/phases/phase1-manual-seed.md
```

## Summary

1. Trace **parent** funding wallets behind Polymarket accounts.
2. **Rank** clusters by a weighted score (profit-heavy; formula in [clustering.md](docs/discovery/clustering.md) / [phase2](docs/phases/phase2-parent-watcher.md)).
3. **Watch** new accounts funded by flagged parents (zero trades required).
4. **Mirror** cluster net exposure in **paper mode** first; live optional later.
5. **Analytics** with sessions, global rollups, and rich event logging.

## License

TBD
