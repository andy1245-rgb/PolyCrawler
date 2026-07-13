# Protocol 2 — Position State Machine (FSM)

**Source:** [phase3a-fsm-and-net.md](../phases/phase3a-fsm-and-net.md) (behavioral spec)
**Related:** [architecture.md](../architecture.md) §5

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
| **WATCHING** | No mirrored hold. Net is flat or we're idle. May still carry `tp_sl_mirror_suspended_until_flat` after a TP/SL exit until net ~0 clears it. Default starting state. |
| **SIGNAL** | Entry rules passed but review required. Awaiting human approve/reject. |
| **IN_POSITION** | We have a mirrored position. Net deltas → adjustments. |
| **CLOSED** | **Bookkeeping only — not a resting state.** Exit logged, then **same poll tick** → `WATCHING`. |
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

### Persisted fields (`cluster_positions`)

| Field | Meaning |
|-------|---------|
| `sibling_balances` | `accountId → { yesShares, noShares }` |
| `net_exposure` | sum(Yes) − sum(No) across siblings |
| `last_known_net` | Previous net for delta mirroring |
| `mirrored_yes` / `mirrored_no` | Our current hold |
| `last_closed_at` | For follow re-entry |
| `tp_sl_mirror_suspended_until_flat` | Set **only** on `tp_hit` / `sl_hit`; cleared when net ~0 |

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
