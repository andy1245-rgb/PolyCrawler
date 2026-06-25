# Component Interfaces

**Source:** docs/architecture.md §4

---

## IngestionAdapter (abstract)

Swap polling ↔ WebSocket without touching the engine.

```python
class RawEvent(BaseModel):
    event_type: Literal['fund', 'birth', 'trade', 'redeem', 'merge_split']
    parent_id: UUID
    account_id: UUID
    market_id: str | None = None
    tx_hash: str
    block_number: int
    timestamp: datetime
    amounts: dict

class IngestionAdapter(ABC):
    @abstractmethod
    async def poll_batch(self) -> list[RawEvent]:
        """All new events since last poll."""

    @abstractmethod
    async def fetch_balances(self, account_ids: list[UUID]) -> dict[UUID, dict[str, dict[str, int]]]:
        """Current Yes/No balances per market per account."""

    @abstractmethod
    async def fetch_orderbook(self, market_id: str, side: str) -> list[dict]:
        """CLOB order book for paper fill pricing."""
```

## ExecutionAdapter (abstract)

Swap paper ↔ live without touching the engine.

```python
class EntrySignal(BaseModel):
    cluster_position_id: UUID
    market_id: str
    side: Literal['yes', 'no']
    shares: int
    max_price: float | None = None

class FillResult(BaseModel):
    success: bool
    filled_shares: int
    avg_price: float
    slippage_bps: int
    book_snapshot: dict | None = None

class ExecutionAdapter(ABC):
    @abstractmethod
    async def execute_entry(self, signal: EntrySignal) -> FillResult: ...

    @abstractmethod
    async def execute_exit(self, signal: EntrySignal) -> FillResult: ...
```

## Engine (central coordinator)

```python
class Engine:
    def __init__(self, ingestion: IngestionAdapter, execution: ExecutionAdapter,
                 config: Config, db: AsyncSession): ...

    async def run_poll_cycle(self):
        """One cycle: poll → event process → reconcile → execute."""
        events = await self.ingestion.poll_batch()
        for event in sorted(events, key=lambda e: e.timestamp):
            await self._process_event(event)
        await self._reconcile_positions()
```

## Design principle

**Execution never touches engine state.** ExecutionAdapter receives signals, returns fill results. Engine routes events and manages the FSM — it doesn't know or care whether fills are real or simulated.
