# Protocol 5 — Review & Autonomy

**Source:** spec.md §9

---

Controls when human approval is required before mirroring a trade.

### Review modes

| Mode | Paper entries | Live entries |
|------|---------------|--------------|
| `all` | Requires human approval | Requires human approval |
| `live_only` (default) | Auto-execute when rules pass | Requires human approval |
| `none` | Auto-execute | Auto-execute |

When review is required, the cluster position stays in `SIGNAL` state until approved → `IN_POSITION` or rejected → `SKIPPED`.

Review mode is independent of execution mode (`observe` / `paper` / `live`).
