# Protocol 2 — Position State Machine (FSM)

**Source:** spec-full.md §6 | docs/architecture.md §5
**Implementation:** [phase3a-fsm-and-net.md](../phases/phase3a-fsm-and-net.md)

---

Each cluster×market pair has a state in `cluster_positions.state`.

### States

```
WATCHING ──► SIGNAL ──► IN_POSITION ──► CLOSED ──► WATCHING
                │                            │
                └──► SKIPPED                 │
                                             │
                     IN_POSITION ────────────┘
                     (net ~0 / TP / SL / resolve)
```

| State | Meaning |
|-------|---------|
| **WATCHING** | No mirrored hold. Net is flat or we're idle. Default starting state. |
| **SIGNAL** | Entry rules passed but review required. Awaiting human approve/reject. |
| **IN_POSITION** | We have a mirrored position. Net deltas → adjustments. |
| **CLOSED** | Position closed. PnL recorded. Auto-transitions to WATCHING same tick. |
| **SKIPPED** | We chose not to mirror (review rejection or manual skip). |

### Transitions

- `WATCHING` → entry rules pass + review required → `SIGNAL`
- `WATCHING` → entry rules pass + no review (paper auto) → `IN_POSITION`
- `SIGNAL` → approved → `IN_POSITION`
- `SIGNAL` → rejected → `SKIPPED`
- `IN_POSITION` → net ~0 / TP / SL / resolve → `CLOSED`
- `IN_POSITION` → net delta → stay `IN_POSITION` (adjust position)
- `CLOSED` → auto → `WATCHING` (same poll tick)
- `SKIPPED` → net ~0 → `WATCHING`

### Optional timeouts

| Config | Effect |
|--------|--------|
| `position.signalExpireMinutes` | `SIGNAL` → `EXPIRED` if no review action |
| `position.marketWatchExpireDays` | `WATCHING` with activity but no entry → expire |

### Implementation approach

```python
class PositionState(str, Enum):
    WATCHING = 'watching'
    SIGNAL = 'signal'
    IN_POSITION = 'in_position'
    CLOSED = 'closed'
    SKIPPED = 'skipped'

class PositionFSM:
    def __init__(self, db_row: ClusterPosition, config: Config):
        ...
```
