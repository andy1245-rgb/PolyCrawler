# Phase 7 — Auto-Discovery

**Source:** spec.md §16.7, §4.3 | docs/architecture.md §12
**Status:** ⬜ Not started
**Prerequisites:** [Phase 3b](phase3b-paper-execution.md) complete (paper engine proven) + [Phase 6](phase6-backtesting.md) (score validation done)

---

## Goal

Replace manual parent seeding with automated cluster-score-based flagging. The system finds its own parents to watch by scanning for wallet clusters that meet discovery criteria. Manual seeding remains available as a fallback, but the system no longer depends on it.

## Spec references

- spec §4.3 — Discovery: flagging parents (minSiblingCount, minClusterScore, fundingHops)
- spec §4.1.1 — Formula validation (enable minClusterScore after validation script confirms variant)
- spec §16.7 — Auto-discovery deliverable
- spec §13 — End-to-end flow (auto-discovery after engine is proven)

## Prerequisites

- Phase 3b complete: paper engine proven profitable
- Phase 6 complete: `validate_scores.py` has confirmed the best score variant and recommended a `min_cluster_score` threshold
- `min_cluster_score` config value set (no longer `null`)
- Phase 2 scoring module (`clustering/scorer.py`) fully working

## Gate condition

**Spec is explicit:** auto-discovery is only enabled after the paper engine is proven. Do NOT start this phase until Phase 3b + Phase 6 validate that the scoring formula and trading rules produce profitable results.

## Modules to build

### 1. `src/poly_crawler/clustering/discovery.py` — Full discovery pipeline

Expands the Phase 2 basic discovery module into full auto-flagging.

**Functions:**

| Function | Purpose |
|----------|---------|
| `async discover_new_parents(session, config) -> list[Parent]` | Scan for new wallet clusters meeting flagging criteria |
| `async should_flag_parent(cluster_score, sibling_count, config) -> bool` | Evaluate flagging rules |
| `async flag_parent(session, parent_address) -> Parent` | Insert parent + create cluster, set watch |
| `async scan_funding_graph(session, start_block, config) -> list[dict]` | Trace funding flows to find clusters |

**Flagging rules (spec §4.3):**

```
if config.discovery.min_cluster_score is not None:
    # min_cluster_score OVERRIDES min_sibling_count
    flag if cluster_score >= min_cluster_score
else:
    # Fallback: simple sibling count rule
    flag if sibling_count >= min_sibling_count
```

### 2. `src/poly_crawler/clustering/tracer.py` — Expanded tracing

Expands Phase 2 tracer to support full funding graph exploration for discovery.

**New functions:**

| Function | Purpose |
|----------|---------|
| `async find_funding_clusters(start_block, end_block, max_hops) -> list[FundingCluster]` | Scan block range for funding patterns |
| `async trace_funding_graph(address, max_hops, visited=None) -> FundingGraph` | Deep funding trace from an address |
| `async identify_polymarket_accounts_in_graph(graph) -> list[str]` | Filter graph nodes to Polymarket accounts |

**FundingCluster:**

```python
@dataclass
class FundingCluster:
    parent_address: str
    sibling_addresses: list[str]
    funding_txs: list[str]
    first_funded_at: datetime
```

### 3. `src/poly_crawler/scheduler/tasks.py` — Discovery task

| Task | Interval | Purpose |
|------|----------|---------|
| `auto_discovery` | 3600s (1 hour, configurable) | Scan for new wallet clusters meeting flagging criteria |

### 4. Update `src/poly_crawler/cli.py` — Discovery commands

| Command | Purpose |
|---------|---------|
| `poly-crawler discover --scan` | Trigger a manual discovery scan |
| `poly-crawler discover --threshold 8.0` | Set `min_cluster_score` at runtime |
| `poly-crawler discover --status` | Show recently discovered parents |

## Data flow

### Auto-discovery cycle

```
1. auto_discovery task fires (every 1 hour)
2. Scan recent blocks for USDC funding patterns
3. For each funding cluster found:
   a. Trace funding graph (up to funding_hops deep)
   b. Identify Polymarket accounts in the graph
   c. If sibling_count >= min_sibling_count (or cluster_score >= min_cluster_score):
      - Flag parent: insert Parent row (is_ignored=false)
      - Create Cluster row
      - Create Account rows for each sibling
      - Compute initial cluster_score
      - Create Alert (alert_type="sibling", "New cluster discovered")
4. Newly flagged parents are immediately watched by parent_watcher (Phase 2)
5. Report: "Discovered 3 new parents this cycle"
```

### Manual seed fallback

```
Manual seeding (Phase 1) still works alongside auto-discovery:
- Manually seeded parents: is_ignored=false, no discovery metadata
- Auto-discovered parents: is_ignored=false, metadata contains discovery info
- Both are watched by the same parent_watcher task
```

## Config changes

| Key | Change | Default |
|-----|--------|---------|
| `discovery.min_cluster_score` | Set to validated threshold (from Phase 6) | Was `null`, now e.g. `8.0` |
| `discovery.auto_discovery_enabled` | New: toggle auto-discovery on/off | `false` (enable after validation) |
| `discovery.scan_interval_sec` | New: how often to scan for new clusters | `3600` (1 hour) |

Add to `DiscoveryConfig` in `schema.py` and `default.yaml`.

## DB changes

None. All tables exist. Discovery writes to: `parents`, `accounts`, `clusters`, `alerts`.

## Test plan

### Unit tests

| File | What it tests |
|------|---------------|
| `tests/unit/test_discovery.py` | should_flag_parent with min_cluster_score; should_flag_parent with min_sibling_count fallback; flagging threshold boundary conditions |

### Integration tests

| File | What it tests |
|------|---------------|
| `tests/integration/test_auto_discovery.py` | Full discovery cycle: mock funding data → cluster found → parent flagged → accounts created → alert logged; manual seed still works alongside; ignored parents excluded |

## Acceptance criteria

- [ ] `discover_new_parents()` scans blocks and finds funding clusters
- [ ] `should_flag_parent()` correctly applies min_cluster_score OR min_sibling_count
- [ ] Flagged parents get Parent + Cluster + Account rows created
- [ ] Discovery alerts created (alert_type="sibling")
- [ ] `auto_discovery` scheduler task runs on interval
- [ ] Manual seeding still works alongside auto-discovery
- [ ] `discovery.min_cluster_score` overrides `min_sibling_count` when set
- [ ] All unit + integration tests pass
- [ ] `ruff check` and `mypy` pass clean

## Open decisions

| # | Question | Notes |
|---|----------|-------|
| 1 | Discovery scan scope | Full block scan is expensive. Should we scan only blocks with USDC Transfer events to known Polymarket contracts? Event-indexed approach vs full scan. |
| 2 | Funding graph depth | `funding_hops: 3` — is this deep enough? Deep traces are RPC-expensive. |
| 3 | Deduplication | How to avoid re-discovering the same parent across scans? Check `parents` table by `chain_address` before flagging. |
| 4 | Discovery metadata | What to store in `parents.metadata`? Suggest: discovery_block, discovery_score, discovery_method (auto/manual). |
| 5 | Rate limiting | Auto-discovery could make many RPC calls. Need rate limiting or budget tracking (open question #3 — RPC provider budget). |
