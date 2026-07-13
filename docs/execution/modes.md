# Execution Modes

**Source:** [phase3b-paper-execution.md](../phases/phase3b-paper-execution.md), [phase8-live-execution.md](../phases/phase8-live-execution.md)
**Implementation:** [phase3b-paper-execution.md](../phases/phase3b-paper-execution.md), [phase8-live-execution.md](../phases/phase8-live-execution.md)

---

| Mode | Detection | Trading | Capital |
|------|-----------|---------|---------|
| `observe` | On | None | $0 |
| `paper` | On | Simulated | $0 |
| `live` | On | Real orders | User funds |

Implementation: shared strategy engine; only swap the **execution adapter** (paper vs live).

See [paper-fill-model.md](paper-fill-model.md) for how paper fills are priced.
