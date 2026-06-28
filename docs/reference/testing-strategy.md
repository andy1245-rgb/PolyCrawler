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

| File | Format | Purpose |
|------|--------|---------|
| `labeled_wallets.json` | JSON | Known parent with 3 sibling accounts, cluster_score 18.3 |
| `sample_events.json` | JSON array | 3 events: fund ($5k), birth (new account), trade (1k yes @ 0.45) |
| `sample_orderbook.json` | JSON | Bid/ask levels for Yes and No on a sample market |
| `__init__.py` | — | Package marker |

Load fixtures in tests:

```python
import json

def test_load_fixtures():
    path = Path(__file__).parent.parent / "fixtures" / "sample_events.json"
    with open(path) as f:
        events = json.load(f)
    assert len(events) == 3
```

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
