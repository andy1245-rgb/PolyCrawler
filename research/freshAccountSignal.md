# Copying fresh accounts' first bets, and copying flagged winners on the same topic

Scripts: `scripts/research/discoveryIdeas2.py`, `scripts/research/freshAndTopic.py`. Data: `data/` plus `data/universe/` (85 events, 3.9M buy entries). Every copy is **$100 at the insider's own price**, settled at resolution.

## 1. Adding the manual-review features to rule A makes it worse

Each is a point-in-time monthly flag, and we copy the flagged accounts' buys the following month.

| Variant | Copies | Events | Return excl. Iran and Venezuela |
|---|---:|---:|---:|
| A base | 7,466 | 75 | −41% |
| A + ladder precision ≥ 0.5 | 5,784 | 74 | −54% |
| A + no losing ladder bets | 4,364 | 61 | −52% |
| A + bet placed ≤ 72h before resolution | 1,042 | 37 | −50% |
| A + precision and lead time | 793 | 34 | −59% |
| A + co-trades with another flagged account | 1,865 | 39 | −72% |

Cleaner insider detection doesn't help, because **what a flagged account does after its win isn't informed**. An insider's edge belongs to one event.

## 2. Same-topic copying

Copying flagged accounts only on markets that share a topic tag with their winning bet (generic tags `politics`, `geopolitics` and `world` ignored): −32% excluding Iran and Venezuela, versus −44% for other-topic buys. That's less bad, but still negative.

## 3. Copying a fresh account's big bet when it's placed

Fresh = account ≤ 3 days old by our own fills, ≤ 3 markets so far. No win is required, so nothing is known in hindsight.

| Rule (excl. Iran and Venezuela) | Copies | Events in profit | Return |
|---|---:|---:|---:|
| anyone ≥ $1k at ≤ 0.30 | 5,982 | 14/69 | −32% |
| anyone ≥ $1k at ≤ 0.50 | 12,272 | 17/72 | −14% |
| anyone ≥ $1k, any price | 94,490 | 42/72 | −2% |
| fresh ≥ $1k at ≤ 0.50 | 3,241 | 17/70 | −4% |
| fresh ≥ $5k at ≤ 0.50 | 563 | 13/49 | +8% |
| fresh ≥ $20k at ≤ 0.50 | 66 | 9/23 | +1% |

Robustness checks for fresh ≥ $5k at ≤ 0.50:

- Without the top 1 event: −9%. Without the top 3: −44%.
- Jun 2024–Jun 2025: +36%. Jun 2025–Oct 2026: −36%.
- Resampling whole events gives a 90% range of −38% to +48%, with a 60% chance the true return is above 0.

The best events were Yoon's removal, Biden dropping out, and ZachXBT/Axiom (a documented insider case).

## Conclusion

- **Outside the Iran and Venezuela military events, nothing tested so far is reliably profitable.** Fresh accounts' large first bets beat the "anyone" benchmark by about 20 points, but the result depends on 1–3 events and flips sign between the two time halves.
- **Where insider edge clearly exists:** military and strike-timing events. Insiders cluster there, the fresh-account plus big-longshot profile fits, and co-trade clusters show up. That category is under-sampled in the universe on purpose: the rest of the 2026 Iran war, Israel strikes and the June 2025 siblings were left out.
- **Next test:** a category-specific strategy, using the fresh-big-bet signal plus co-trade clusters on military and strike events only, fetched across many such events over time and validated with event-level resampling.
