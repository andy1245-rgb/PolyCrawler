# PolyCrawler

Detection and paper-trading pipeline for Polymarket accounts linked by on-chain funding (parent wallets → sibling accounts → early alerts before wins).

**Status:** v0.1.5 — Phase 0–1 complete. Manual seed CLI is live; next is Phase 2 (parent watcher + scoring).

## Spec

See [spec.md](./spec.md) for product behavior, protocols, configuration defaults, and implementation phases.

## Quick start (local)

```bash
pip install -e ".[dev]"
cp .env.example .env
# Start Postgres, then:
make setup-db    # create DB + alembic upgrade + schema check
make test
poly-crawler seed --parent 0xABC...   # Phase 1 manual seed
poly-crawler seed --list
make run         # http://localhost:8000/health
```

## Summary

1. Trace **parent** funding wallets behind Polymarket accounts.
2. **Rank** clusters by a weighted score (profit-heavy; formula candidate in spec).
3. **Watch** new accounts funded by flagged parents (zero trades required).
4. **Mirror** target buys/sells in **paper mode** first; live optional later.
5. **Analytics** with sessions, global rollups, and rich event logging.

## License

TBD
