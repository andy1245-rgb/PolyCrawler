# Discovery step 1 — threshold sensitivity

Scored on `data/suspicious.parquet` from `configs/insiderCases.yaml` (`splitDate` 2026-03-01, `maxAccountAgeDays` 14, `minBetUsd` 1000). No refetch. Each account is scored on its largest winning buy.

The run had 6671 accounts with a winning bet ≥ $1000. That exceeded 3000, so enrichment kept only accounts that also have a winning bet with `avgBuyPrice` ≤ 0.7 (1842). Favorite-only winners are not in this table. `marketsTraded` above 30 is a lower bound (activity paging stops once `isFocused` cannot pass a cap of 30); every labeled wallet below is under that cap, so those counts are exact.

Recall is labeled wallets flagged suspicious / 9 labeled wallets (all nine case events are in `data/markets.parquet`).

| maxMarketsTraded | maxBuyPrice | minSignals | suspicious | recall |
|---:|---:|---:|---:|---:|
| 5 | 0.3 | 3 | 350 | 9/9 |
| 5 | 0.3 | 4 | 102 | 4/9 |
| 5 | 0.5 | 3 | 432 | 9/9 |
| 5 | 0.5 | 4 | 150 | 4/9 |
| 5 | 0.7 | 3 | 520 | 9/9 |
| 5 | 0.7 | 4 | 168 | 4/9 |
| 15 | 0.3 | 3 | 484 | 9/9 |
| 15 | 0.3 | 4 | 187 | 7/9 |
| 15 | 0.5 | 3 | 562 | 9/9 |
| 15 | 0.5 | 4 | 265 | 7/9 |
| 15 | 0.7 | 3 | 652 | 9/9 |
| 15 | 0.7 | 4 | 305 | 7/9 |
| 30 | 0.3 | 3 | 560 | 9/9 |
| 30 | 0.3 | 4 | 222 | 9/9 |
| 30 | 0.5 | 3 | 653 | 9/9 |
| 30 | 0.5 | 4 | 312 | 9/9 |
| 30 | 0.7 | 3 | 762 | 9/9 |
| 30 | 0.7 | 4 | 365 | 9/9 |

Config default for this file is the 15 / 0.3 / 4 row (187 suspicious, 7/9). The two misses are Courteous-Epoch (18 markets before the split) and Aware-Initialize (24). Both are new, longshot, and big, so `minSignals` 3 flags them, and so does `maxMarketsTraded` 30 with `minSignals` 4. A cap of 5 drops Lettucehead718, suffix-295, and fuego66 (10, 10, and 11 markets).
