# Database Schema

**Source:** spec.md §19 | docs/architecture.md §2

---

11 tables defined in `src/poly_crawler/db/models/`.

## Tables

### `parents`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| chain_address | VARCHAR(42) | Unique, indexed |
| first_seen_at | Timestamp | |
| last_seen_at | Timestamp | |
| is_ignored | Boolean | Indexed |
| metadata_ | JSONB | |

Relationships: `accounts` (1:N), `cluster` (1:1).

### `accounts`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| polymarket_address | VARCHAR | Unique |
| account_type | ENUM | deposit_wallet / safe / proxy / unknown |
| parent_id | UUID FK | Indexed |
| watch_status | ENUM | active / expired, indexed |
| first_funded_at | Timestamp | |
| last_activity_at | Timestamp | |
| metadata_ | JSONB | |

### `clusters`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| parent_id | UUID FK | Unique |
| cluster_score | Float | |
| score_variant | ENUM | sqrt / log / piecewise |
| last_scored_at | Timestamp | |
| sibling_count | Integer | |
| vetted_sibling_count | Integer | |

### `cluster_positions`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| cluster_id | UUID FK | Indexed |
| market_id | VARCHAR | |
| market_slug | VARCHAR | |
| market_title | VARCHAR | |
| market_tags | JSONB | |
| state | ENUM | watching / signal / in_position / closed / skipped |
| net_exposure | BIGINT | |
| last_known_net | BIGINT | |
| mirrored_yes | BIGINT | |
| mirrored_no | BIGINT | |
| sibling_balances | JSONB | |
| tp_sl_suspended | Boolean | |
| last_closed_at | Timestamp | |
| last_closed_reason | VARCHAR | |
| config_snapshot_id | UUID FK | |

Unique: `(cluster_id, market_id)`.

### `alerts`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| parent_id | UUID FK | Indexed |
| account_id | UUID FK | |
| cluster_id | UUID FK | Indexed |
| alert_type | ENUM | fund / birth / sibling / conflict / conflict_resolved / signal / entry / exit |
| amount_usd | Float | |
| cluster_score_at_event | Float | |
| rank | Integer | |
| metadata_ | JSONB | |
| is_false_positive | Boolean | Nullable, indexed |

### `paper_trades`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| cluster_position_id | UUID FK | Indexed |
| session_id | UUID FK | Indexed |
| event_type | ENUM | entry / net_adjustment / exit |
| sibling_account_id | UUID FK | |
| net_before | BIGINT | |
| net_after | BIGINT | |
| net_delta | BIGINT | |
| our_side | ENUM | yes / no |
| our_shares | BIGINT | |
| our_fill_price | Float | VWAP from orderbook walk |
| our_fill_usd | Float | Total cost |
| source_tx | VARCHAR | |
| reason | VARCHAR | |
| latency_ms | Integer | Signal → fill |
| book_snapshot_id | VARCHAR | |
| slippage_bps | Integer | VWAP vs mid |

### `sibling_balance_snapshots`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| account_id | UUID FK | Indexed |
| cluster_id | UUID FK | |
| market_id | VARCHAR | |
| yes_shares | BIGINT | |
| no_shares | BIGINT | |
| polled_at | Timestamp | |

### `sessions`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR | |
| mode | ENUM | observe / paper / live |
| review_mode | ENUM | all / live_only / none |
| config_snapshot | JSONB | Immutable copy |
| private | Boolean | |
| started_at | Timestamp | |
| ended_at | Timestamp | |
| status | ENUM | running / completed / aborted |

### `config_snapshots`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| config_json | JSONB | |
| created_at | Timestamp | |

### `rpc_logs`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| method | VARCHAR | |
| params | Text | |
| provider | VARCHAR | |
| latency_ms | Integer | |
| error | Text | |
| created_at | Timestamp | |

### `backtest_runs`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| session_id | UUID FK | |
| config_snapshot | JSONB | |
| score_variant | VARCHAR | |
| started_at | Timestamp | |
| completed_at | Timestamp | |
| status | ENUM | running / completed / failed |

## Entity relationships

```
parents ──1:1── clusters
parents ──1:N── accounts
clusters ──1:N── cluster_positions
cluster_positions ──1:N── paper_trades
sessions ──1:N── paper_trades
accounts ──1:N── sibling_balance_snapshots
alerts ──N:1── parents
alerts ──N:1── accounts
alerts ──N:1── clusters
```
