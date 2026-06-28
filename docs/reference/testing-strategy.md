# Testing Strategy

**Source:** docs/architecture.md §11

---

7 unit test files + 3 integration test files planned.

## Test infrastructure

### conftest.py (`tests/conftest.py`)

Shared fixtures used by every test file:

| Fixture | What it provides |
|---------|-----------------|
| `engine` | In-memory SQLite `AsyncEngine` with all tables created |
| `session` | `AsyncSession` backed by the in-memory engine |
| `parent_kwargs` | Default kwargs dict for constructing a `Parent` |
| `account_kwargs` | Default kwargs dict for constructing an `Account` |
| `cluster_kwargs` | Default kwargs dict for constructing a `Cluster` |
| `session_kwargs` | Default kwargs dict for constructing a `Session` |
| `config_snapshot_kwargs` | Default kwargs dict for constructing a `ConfigSnapshot` |

Tests construct model instances by passing factory kwargs:

```python
async def test_create_parent(session, parent_kwargs):
    parent = Parent(**parent_kwargs)
    session.add(parent)
    await session.commit()
    assert parent.chain_address == parent_kwargs["chain_address"]
```

### Test fixtures (`tests/fixtures/`)

> **Status:** The JSON fixture files below are **planned** for Phases 1–3 (they'll be created alongside the tests that use them). Currently only `__init__.py` exists as a package marker.

| File | Format | Planned Phase | Purpose |
|------|--------|---------------|---------|
| `labeled_wallets.json` | JSON | Phase 1+ | Known parent with 3 sibling accounts, cluster_score 18.3 |
| `sample_events.json` | JSON array | Phase 1+ | 3 events: fund ($5k), birth (new account), trade (1k yes @ 0.45) |
| `sample_orderbook.json` | JSON | Phase 3+ | Bid/ask levels for Yes and No on a sample market |
| `__init__.py` | — | Complete | Package marker |

## Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_scorer.py` | Score variants A/B/C with known inputs |
| `tests/unit/test_state_machine.py` | FSM transitions for all states |
| `tests/unit/test_entry_rules.py` | minBuyUsd gate, maxOdds, marketTags allowlist, condition combos |
| `tests/unit/test_exit_rules.py` | Net flat, TP, SL, max hold, resolution |
| `tests/unit/test_net_calculator.py` | Net exposure, deltas, mirror target sizing |
| `tests/unit/test_hedge_filter.py` | net_only vs filter_before_net on same-fill hedges |
| `tests/unit/test_reentry.py` | Follow re-entry window and edge cases |

## Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_ingestion_polling.py` | Polling adapter with mock RPC |
| `tests/integration/test_engine_cycle.py` | Full poll cycle with all components wired |
| `tests/integration/test_paper_execution.py` | Orderbook walk with mock CLOB data, fill accuracy |

## Running tests

```bash
# All tests
pytest -v

# With coverage
pytest --cov=src/poly_crawler --cov-report=term-missing

# Single file
pytest tests/unit/test_scorer.py -v
```
