# Testing Strategy

**Source:** docs/architecture.md §11

---

7 unit test files + 3 integration test files planned.

## Unit tests

| File | What it tests |
|------|---------------|
| `test_scorer.py` | Score variants A/B/C with known inputs |
| `test_state_machine.py` | FSM transitions for all states |
| `test_entry_rules.py` | minBuyUsd gate, maxOdds, marketTags allowlist, condition combos |
| `test_exit_rules.py` | Net flat, TP, SL, max hold, resolution |
| `test_net_calculator.py` | Net exposure, deltas, mirror target sizing |
| `test_hedge_filter.py` | net_only vs filter_before_net on same-fill hedges |
| `test_reentry.py` | Follow re-entry window and edge cases |

## Integration tests

| File | What it tests |
|------|---------------|
| `test_ingestion_polling.py` | Polling adapter with mock RPC |
| `test_engine_cycle.py` | Full poll cycle with all components wired |
| `test_paper_execution.py` | Orderbook walk with mock CLOB data, fill accuracy |

## Fixtures

- `labeled_wallets.json` — known parent→account→cluster test data
- `sample_events.json` — fund, birth, trade event sequences
- `sample_orderbook.json` — CLOB order books at various depths
