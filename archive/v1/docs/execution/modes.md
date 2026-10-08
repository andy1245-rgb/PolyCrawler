# Execution Modes

**Source:** spec.md §10

---

| Mode | Detection | Trading | Capital |
|------|-----------|---------|---------|
| `observe` | On | None | $0 |
| `paper` | On | Simulated | $0 |
| `live` | On | Real orders | User funds |

Implementation: shared strategy engine; only swap the **execution adapter** (paper vs live).

See [paper-fill-model.md](paper-fill-model.md) for how paper fills are priced.
