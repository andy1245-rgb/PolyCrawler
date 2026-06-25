# Cluster Scoring & Discovery

**Source:** spec.md §4 | docs/architecture.md §9

---

## Cluster score

A weighted quality metric for a parent + sibling group. Used **only** for discovery ranking and alert priority — **not** for trade entry gating.

Score components (configurable weights):

| Component | Weight | Meaning |
|-----------|--------|---------|
| Profit | 2.0 | Total realized profit across siblings |
| Efficiency | 15.0 | Profit ÷ total capital deployed |
| Win rate | 5.0 | Winning trades ÷ total closed trades |

Score formula variants:

| Variant | Behavior | Default |
|---------|----------|---------|
| `sqrt` | sqrt(profit) × weight + ... | **Yes** |
| `log` | log10(1 + profit) × weight + ... | No |
| `piecewise` | Linear up to cap, then log | No |

Discovery filters: `min_sibling_count`, `min_cluster_score`, `funding_hops`.

## Architecture

Planned modules in `src/poly_crawler/clustering/`:
- `tracer.py` — Follow funding chains from parent to sibling accounts
- `scorer.py` — Score variants A/B/C with configurable weights
- `discovery.py` — Auto-discovery and parent flagging logic
