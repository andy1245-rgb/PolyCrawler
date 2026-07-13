# Phase 1 — Manual Seed

**Status:** ✅ Complete
**Prerequisites:** [Phase 0](phase0-bootstrap.md) complete
**Human-readable docs:** [clustering.md](../discovery/clustering.md) (manual seed section), [end-to-end-flow.md](../operations/end-to-end-flow.md)

---

## Goal

Provide a CLI to hand-pick 5–10 parent wallets from research and insert them into the database. Each seeded parent gets a `clusters` row so it is ready for the parent watcher (Phase 2). No chain interaction — DB writes only.

---

## Behavioral specification

### Manual seed is always supported

Auto-discovery (Phase 7) supplements but never replaces manual seed. Researchers can flag parents before the scoring formula is validated.

### Parent flagging (manual path)

From discovery rules:

```yaml
discovery:
  minSiblingCount: 2       # auto-flag uses this; manual seed bypasses
  minClusterScore: null      # when set (Phase 7), overrides minSiblingCount
  fundingHops: 3
```

**Manual seed behavior:**

1. User provides one or more parent wallet addresses (CLI flag or file).
2. System validates Ethereum address format (42 chars, valid checksum via `eth-account`).
3. For each new address: insert `parents` row (`is_ignored=false`), create linked `clusters` row (`cluster_score=0.0`, `score_variant="sqrt"`).
4. Duplicate addresses are skipped (unique constraint on `chain_address`).
5. `--ignore` sets `is_ignored=true` — excluded from watch and alert ranking.

### What manual seed does NOT do

- Does not trace siblings or fetch chain data (Phase 2).
- Does not create `accounts` rows until FUND/BIRTH events arrive.
- Does not trigger trades or alerts.

### End-to-end context

Manual seed is step 1 of the v0.1 pipeline:

```
MANUAL parent seed → parent watcher → rank by clusterScore → watch cluster → …
```

---

## Implementation

### Modules to build

#### 1. `src/poly_crawler/cli.py`

| Command | Purpose |
|---------|---------|
| `poly-crawler seed --parent 0xABC...` | Insert parent + cluster (repeatable flag) |
| `poly-crawler seed --from-file parents.txt` | Bulk seed (one address per line) |
| `poly-crawler seed --list` | Show seeded parents and cluster scores |
| `poly-crawler seed --ignore 0xABC...` | Set `is_ignored: true` |

#### 2. `src/poly_crawler/db/repositories/parent_repo.py`

| Function | Purpose |
|----------|---------|
| `create_parent(session, chain_address) -> Parent` | Insert parent |
| `create_cluster_for_parent(session, parent_id) -> Cluster` | 1:1 cluster row |
| `get_parent_by_address(session, chain_address) -> Parent \| None` | Lookup |
| `list_parents(session, include_ignored=False) -> list[Parent]` | List |
| `ignore_parent(session, chain_address) -> None` | Set ignored |

### Data flow

```
poly-crawler seed --parent 0xABC...
  → load_config() → init_engine()
  → for each address: validate → insert Parent → insert Cluster → commit
  → print summary
```

---

## Config changes

None.

---

## DB changes

None — writes to existing `parents` and `clusters` tables only.

---

## Test plan

### Unit — `tests/unit/test_parent_repo.py`

- Create parent, duplicate constraint, cluster creation, lookup, list with ignore filter, ignore_parent

### Integration — `tests/integration/test_seed_cli.py`

- Single/multiple seed, file input, duplicate skip, `--list`

---

## Acceptance criteria

- [x] `pip install -e ".[dev]"` installs `poly-crawler` CLI
- [x] `poly-crawler seed --parent 0x…` creates `parents` + `clusters` rows
- [x] `poly-crawler seed --list` shows seeded parents
- [x] `poly-crawler seed --ignore 0x…` sets `is_ignored=true`
- [x] Duplicate addresses do not create duplicates
- [x] Invalid addresses rejected
- [x] All tests pass; `ruff` and `mypy` clean

---

## Open decisions

| # | Question | Resolution |
|---|----------|------------|
| 1 | Click vs Typer | **Typer** — async-friendly, type hints |
| 2 | Fetch siblings on seed? | **No** — Phase 2 |
| 3 | Validate checksums? | **Yes** — `eth-account` |
