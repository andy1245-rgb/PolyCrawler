# Paper Fill Model — Orderbook Walk

**Source:** spec.md §10.1 | docs/architecture.md §8

---

## The problem

When a sibling trade triggers an entry signal, we need to simulate what price *we* would have gotten if we mirrored it. We can't use the sibling's fill price — by the time we detect, poll, and act, the book has moved. We also can't assume the mid price — there might not be enough liquidity there for our size.

The paper fill model exists to give honest, conservative price estimates.

## The algorithm

Paper entries and exits use **next-poll timing** — not the signal instant price.

```
Target: mirror 5000 Yes shares on market XYZ

Step 1 — Wait for next poll cycle after the signal.

Step 2 — Fetch CLOB order book for the Yes side.
         Level 1: 2000 shares @ $0.45  (nearest mid = cheapest)
         Level 2: 4000 shares @ $0.47
         Level 3: 1000 shares @ $0.50

Step 3 — Walk the book from cheapest up, consuming shares:
         Take all 2000 @ $0.45   → cost = 2000 × 0.45  = $900,   remaining = 3000
         Take 3000 of 4000 @ $0.47 → cost = 3000 × 0.47 = $1410, remaining = 0

Step 4 — Compute blended price:
         total_cost  = $900 + $1410 = $2310
         avg_price   = $2310 / 5000 shares = $0.462
```

## What is VWAP?

**VWAP = Volume-Weighted Average Price = total dollars paid ÷ total shares filled**

It's the *real* average price when you buy in pieces across multiple price levels, instead of assuming one price at the top of the book.

In the example:
- You didn't get all 5000 at $0.45 — only 2000 existed there
- You didn't need all 4000 at $0.47 — only 3000 to finish
- Your blended cost is **$0.462**, between the two levels

That's VWAP: the price-weighted-by-volume average. It's what any real execution engine actually pays.

## Slippage

Compare VWAP to the mid price:

```
mid = (bid + ask) / 2
slippage_bps = |VWAP - mid| / mid × 10000
```

Example: bid=$0.44, ask=$0.46 → mid=$0.45
```
|0.462 - 0.45| / 0.45 × 10000 = ~27 bps
```

The paper fill got 0.27% worse than mid due to walking into thinner liquidity. That's realistic slippage baked into paper PnL.

## Pessimistic slippage knob

```yaml
paper:
  fill_model: orderbook_walk_next_poll
  pessimistic_slippage_pct: 0.0   # extra adverse adjustment on top
```

Set to e.g. 0.1 (10%) to make paper fills more conservative than the walk suggests.

## Pseudocode

```python
async def walk_orderbook(api, market_id, side, target_shares):
    book = await api.get_orderbook(market_id, side)
    remaining = target_shares
    total_cost = 0.0
    levels = []

    for level in sorted(book['levels'], key=lambda l: l['price']):
        fill = min(remaining, level['shares'])
        total_cost += fill * level['price']
        remaining -= fill
        levels.append(level)
        if remaining <= 0:
            break

    avg_price = total_cost / target_shares
    mid = (book['bid'] + book['ask']) / 2
    slippage = int(abs(avg_price - mid) / mid * 10000)

    return FillResult(
        success=remaining == 0,
        filled_shares=target_shares - remaining,
        avg_price=avg_price,
        slippage_bps=slippage,
        book_snapshot={'levels': levels},
    )
```

## DB: what gets stored

In `paper_trades`:
- `our_fill_price` — the VWAP from the walk
- `our_fill_usd` — total cost
- `our_shares` — shares filled
- `slippage_bps` — VWAP vs mid
- `book_snapshot_id` — raw book levels reference
