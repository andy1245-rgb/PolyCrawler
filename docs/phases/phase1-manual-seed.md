# Phase 1 — Manual Seed

**Source:** spec.md §16.1 | docs/architecture.md §12
**Status:** ⬜ Not started
**Prerequisites:** [Phase 0](phase0-bootstrap.md) complete

---

## Goal

Provide a CLI to hand-pick 5–10 parent wallets from research and insert them into the database. Each seeded parent gets a `clusters` row so it's immediately ready for the parent watcher (Phase 2). This is the simplest phase — no chain interaction, no polling, just DB writes and a command interface.

## Spec references

- spec §4.3 — Discovery: flagging parents (manual seed list always supported)
- spec §16.1 — Manual seed deliverable
- spec §13 — End-to-end flow (starts with manual parent seed)

## Prerequisites

- Phase 0 complete (DB models, config, engine all working)
- `[project.scripts]` entry point added to `pyproject.toml` (pre-flight fix from [_index.md](_index.md))
- `aiosqlite` installed (pre-flight fix — already done)
- A local Postgres running OR willingness to use the default `localhost:5432`

## Modules to build

### 1. CLI entry point — `src/poly_crawler/cli.py`

A Click or Typer-based CLI that provides the `seed` command. This is the first user-facing interface beyond `uvicorn`.

**Commands:**

| Command | Purpose |
|---------|---------|
| `poly-crawler seed --parent 0xABC... [--parent 0xDEF...]` | Insert parent wallets + create cluster rows |
| `poly-crawler seed --from-file parents.txt` | Bulk seed from a file (one address per line) |
| `poly-crawler seed --list` | Show all seeded parents and their cluster scores |
| `poly-crawler seed --ignore 0xABC...` | Set `is_ignored: true` on a parent |

**Interface:**

```python
# src/poly_crawler/cli.py
import asyncio
import typer
from poly_crawler.config import load_config
from poly_crawler.db import init_engine, get_session

app = typer.Typer()

@app.command()
def seed(parent: list[str] = typer.Option(None), from_file: str = typer.Option(None)):
    """Seed parent wallets into the database."""
    asyncio.run(_seed(parents, from_file))

async def _seed(addresses: list[str], from_file: str | None):
    config = load_config()
    init_engine(config)
    # ... insert Parent + Cluster rows
```

### 2. Seed repository — `src/poly_crawler/db/repositories/parent_repo.py`

A thin repository layer for parent/cluster DB operations. Keeps the CLI and future modules clean.

**Functions:**

| Function | Purpose |
|----------|---------|
| `create_parent(session, chain_address) -> Parent` | Insert a parent, return the ORM object |
| `create_cluster_for_parent(session, parent_id) -> Cluster` | Create the 1:1 cluster row |
| `get_parent_by_address(session, chain_address) -> Parent | None` | Lookup |
| `list_parents(session, include_ignored=False) -> list[Parent]` | List all seeded parents |
| `ignore_parent(session, chain_address) -> None` | Set `is_ignored: true` |

**New directory:** `src/poly_crawler/db/repositories/`

### 3. pyproject.toml — CLI entry point

Add to `pyproject.toml`:

```toml
[project.scripts]
poly-crawler = "poly_crawler.cli:app"
```

### 4. Typer dependency

Add `typer>=0.12.0` to core dependencies in `pyproject.toml`.

## Data flow

```
User runs: poly-crawler seed --parent 0xABC... --parent 0xDEF...
    │
    ▼
load_config() → init_engine(config)
    │
    ▼
For each address:
    1. Check if parent already exists (by chain_address)
    2. If not, insert Parent row (chain_address, is_ignored=false, metadata={})
    3. Create Cluster row (parent_id, cluster_score=0.0, score_variant="sqrt")
    4. Commit
    │
    ▼
Print summary: "Seeded 2 parents. Use --list to view."
```

## Config changes

None. This phase uses existing config + DB models.

## DB changes

None. All tables already exist from the Phase 0 migration. This phase only writes data, not schema.

## Test plan

### Unit tests — `tests/unit/test_parent_repo.py`

| Test | What it verifies |
|------|-----------------|
| `test_create_parent` | Parent inserted with correct chain_address, is_ignored=false |
| `test_create_parent_duplicate_address` | Unique constraint on chain_address raises |
| `test_create_cluster_for_parent` | Cluster created with parent_id, score 0.0, variant "sqrt" |
| `test_get_parent_by_address` | Lookup by chain_address returns correct parent |
| `test_get_parent_by_address_not_found` | Returns None for unknown address |
| `test_list_parents_excludes_ignored` | Ignored parents filtered out by default |
| `test_ignore_parent` | Sets is_ignored=true |

### Integration tests — `tests/integration/test_seed_cli.py`

| Test | What it verifies |
|------|-----------------|
| `test_seed_single_parent` | CLI creates parent + cluster via Typer's CliRunner |
| `test_seed_multiple_parents` | Multiple --parent flags work |
| `test_seed_from_file` | File input works (one address per line) |
| `test_seed_duplicate_skipped` | Seeding an existing address doesn't duplicate |
| `test_seed_list` | --list shows all parents |

## Acceptance criteria

- [ ] `pip install -e ".[dev]"` installs `poly-crawler` CLI command
- [ ] `poly-crawler seed --parent 0xABC...` creates a `parents` row + `clusters` row
- [ ] `poly-crawler seed --list` shows seeded parents
- [ ] `poly-crawler seed --ignore 0xABC...` sets `is_ignored: true`
- [ ] Seeding the same address twice doesn't create duplicates
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Click vs Typer for CLI | Typer recommended — async-friendly, type hints, FastAPI ecosystem alignment |
| 2 | Should seed also fetch initial sibling accounts from chain? | No — that's Phase 2's job (parent watcher). Phase 1 is manual seed only. |
| 3 | Should we validate address checksums? | Yes — reject invalid Ethereum addresses (not 42 chars, bad checksum). Use `eth-account` for validation. |
