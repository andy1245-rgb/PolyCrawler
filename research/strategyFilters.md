# Copy-filter scan (forward sample)

Sample: BUY entries on or after 2026-03-01 by the 236 accounts flagged with pre-split data, in markets with a known winner. Entries = an account's fills on one market/outcome merged when less than 10 minutes apart. We copy each entry with **$100 at the insider's own price**, so there's no delay and no slippage. The price-move check shows delay barely moves price, so this is a fair first pass.

**Only 4 events (in practice 2) are in this sample.** Every row below is dominated by `us-x-iran-ceasefire-by` (+$84.9k) versus `will-the-iranian-regime-fall-by-march-31` (−$15.0k). Without the top event, every filter is negative.

| Filter | n | Win rate | PnL ($100/copy) | Return | Without top event |
|---|---:|---:|---:|---:|---:|
| all | 449 | 37% | 69,303 | 154% | −15,561 |
| price < 0.10 | 103 | 28% | 60,017 | 583% | −5,100 |
| price 0.10–0.20 | 109 | 22% | 5,697 | 52% | −6,500 |
| price 0.20–0.35 | 92 | 43% | 6,809 | 74% | −3,900 |
| price 0.35–0.50 | 20 | 65% | 1,275 | 64% | −200 |
| price 0.50–0.70 | 41 | 41% | −1,287 | −31% | −1,348 |
| price ≥ 0.70 | 84 | 51% | −3,208 | −38% | −3,286 |
| insider bet ≥ $1k | 147 | 43% | 10,968 | 75% | −3,490 |
| insider bet ≥ $5k | 34 | 47% | 991 | 29% | −300 |
| ≥ 2 flagged accounts on same side within 24h | 301 | 31% | 53,092 | 176% | −13,167 |
| price ≤ 0.35 and ≥ 2 flagged accounts | 230 | 29% | 55,894 | 243% | −13,000 |
| largest bet so far per account per event | 131 | 36% | 226 | 2% | −3,977 |

## Takeaways

- **Direction matches the insider theory:** longshots (≤ 0.35) make money and favorites (≥ 0.5) lose. But this comes from 2 events, so it's a hypothesis to test, not a result.
- **Copying only the largest bet per event hurts.** The big bets were the hedged favorites; the payoff came from the small longshot tickets on the date ladder.
- **Bigger insider bets don't help**, and neither does more consensus among flagged accounts.
- **The bottleneck is the number of independent events, not filter tuning.** The next steps are the wider event universe plus rolling monthly discovery, so each filter is judged on dozens of events.
