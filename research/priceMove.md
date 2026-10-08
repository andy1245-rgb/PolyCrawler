# Price-move check

If we buy the same outcome as a suspected insider after a delay, is there still a profit at 1h, 1d, and resolution?

Our entry price is the last trade at or before `entryTs + delay`, plus 50 bps slippage (`price × bps / 10000`). A print older than 6 hours is missing. An account's buys of one outcome are one entry while they fall within 10 minutes of the first fill; the entry time is that first fill and its weight is size × price. Return per $1 is `(exitPrice − ourEntryPrice) / ourEntryPrice`. Timed exits use the same 6-hour mark. Resolution pays $1 when that outcome won and $0 when it lost, and only when `resolvedAt` is after the delayed entry time. The 95% interval is a 1000-draw bootstrap of the equal-weight mean (seed 0), drawn in delay-then-horizon order. Dollar-weighted means use the insider's entry usd. Win rate is the share of priced entries with return > 0. `n` is entries with both an entry price and an exit price.

Tape: 4,624,089 fills, 174 markets, 2,925,468 price points (direct prints plus complements).

A trade at price p on one outcome is also a print at 1 − p on the other outcome of that same market. Each market is its own Yes/No pair. The direct print wins when both exist at one timestamp.

## Labeled wallets

Nine news-linked wallets. This copies every clustered buy on the tape, including the trades that made them known.

9 accounts, 9 with an entry, 354 entries, $590,607 insider usd.

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 354 | 3.92% | -0.50% | 35.88% | [0.06%, 8.21%] | 1.26% |
| 0s | 6h | 354 | 33.31% | 0.63% | 55.93% | [19.78%, 48.85%] | 40.37% |
| 0s | 1d | 265 | 30.84% | 1.78% | 60.00% | [13.20%, 53.42%] | 55.44% |
| 0s | resolution | 354 | 250.06% | 2.32% | 58.76% | [180.78%, 332.30%] | 360.59% |
| 30s | 1h | 354 | 4.47% | -0.50% | 36.44% | [0.86%, 8.63%] | 2.41% |
| 30s | 6h | 354 | 34.73% | 0.65% | 56.50% | [21.14%, 48.71%] | 43.13% |
| 30s | 1d | 265 | 43.82% | 1.83% | 60.38% | [12.82%, 89.17%] | 58.30% |
| 30s | resolution | 354 | 267.46% | 2.26% | 58.76% | [183.01%, 354.05%] | 362.55% |
| 1m | 1h | 354 | 4.06% | -0.50% | 37.01% | [0.54%, 8.21%] | 1.14% |
| 1m | 6h | 354 | 33.29% | 0.59% | 55.65% | [20.34%, 47.85%] | 40.86% |
| 1m | 1d | 265 | 43.02% | 1.71% | 60.00% | [14.14%, 84.03%] | 56.72% |
| 1m | resolution | 354 | 265.98% | 2.16% | 58.76% | [188.01%, 356.48%] | 360.37% |
| 5m | 1h | 354 | 4.23% | -0.50% | 33.33% | [0.57%, 8.41%] | 1.31% |
| 5m | 6h | 354 | 33.87% | 0.53% | 55.08% | [20.27%, 48.73%] | 42.98% |
| 5m | 1d | 265 | 43.55% | 1.67% | 60.38% | [14.85%, 84.14%] | 57.57% |
| 5m | resolution | 354 | 268.30% | 2.00% | 58.76% | [189.60%, 361.20%] | 364.97% |
| 15m | 1h | 354 | 2.08% | -0.50% | 33.90% | [-0.68%, 5.41%] | 1.15% |
| 15m | 6h | 354 | 32.15% | 0.21% | 53.39% | [19.52%, 47.31%] | 43.68% |
| 15m | 1d | 265 | 42.13% | 1.71% | 60.38% | [12.42%, 84.17%] | 61.38% |
| 15m | resolution | 354 | 267.81% | 1.59% | 58.76% | [190.53%, 361.78%] | 372.92% |
| 1h | 1h | 354 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 354 | 30.08% | -0.19% | 49.44% | [16.34%, 45.16%] | 41.30% |
| 1h | 1d | 265 | 40.54% | 1.76% | 61.51% | [12.51%, 79.14%] | 55.02% |
| 1h | resolution | 354 | 284.35% | 1.53% | 55.08% | [189.42%, 393.93%] | 363.84% |

Resolution: 0s mean 250.06% (usd-weighted 360.59%, n=354); 1m mean 265.98% (usd-weighted 360.37%, n=354); 5m mean 268.30% (usd-weighted 364.97%, n=354); 1h mean 284.35% (usd-weighted 363.84%, n=354).

Price move from the entry print: 60s median 0.00%, mean -0.23%, mean price change -0.0000 (271/354 newer prints, 197/354 changed price); 5m median 0.00%, mean -0.25%, mean price change +0.0012 (325/354 newer prints, 261/354 changed price).

Leave-one-market-out drops the largest delay-0 resolution dollar PnL (US strikes Iran by February 28, 2026?, 66 entries, $1,022,228 of $2,129,675, 48% of dollar PnL).

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 288 | 0.58% | -0.50% | 34.38% | [-2.22%, 3.74%] | -0.34% |
| 0s | 6h | 288 | 16.71% | 0.63% | 57.29% | [6.68%, 28.30%] | 31.27% |
| 0s | 1d | 224 | 17.51% | 1.12% | 54.91% | [0.72%, 37.85%] | 39.52% |
| 0s | resolution | 288 | 195.95% | 0.05% | 50.69% | [120.28%, 294.62%] | 264.17% |
| 30s | 1h | 288 | 1.09% | -0.50% | 33.33% | [-1.78%, 4.17%] | -0.17% |
| 30s | 6h | 288 | 18.04% | 0.65% | 57.99% | [6.78%, 30.72%] | 33.49% |
| 30s | 1d | 224 | 32.33% | 1.13% | 55.36% | [1.51%, 77.69%] | 40.33% |
| 30s | resolution | 288 | 214.58% | 0.00% | 50.69% | [118.83%, 322.24%] | 251.74% |
| 1m | 1h | 288 | 0.85% | -0.50% | 34.03% | [-1.89%, 3.87%] | -1.39% |
| 1m | 6h | 288 | 17.33% | 0.59% | 56.94% | [6.76%, 29.08%] | 31.89% |
| 1m | 1d | 224 | 31.61% | 1.12% | 55.36% | [0.00%, 77.81%] | 38.67% |
| 1m | resolution | 288 | 214.79% | 0.10% | 50.69% | [121.52%, 320.52%] | 253.75% |
| 5m | 1h | 288 | 0.74% | -0.50% | 29.17% | [-1.90%, 3.92%] | -1.39% |
| 5m | 6h | 288 | 17.29% | 0.55% | 55.90% | [6.60%, 29.91%] | 33.67% |
| 5m | 1d | 224 | 31.16% | 1.09% | 55.36% | [-0.34%, 80.55%] | 38.85% |
| 5m | resolution | 288 | 214.99% | 0.05% | 50.69% | [120.39%, 322.44%] | 258.32% |
| 15m | 1h | 288 | -0.87% | -0.50% | 29.86% | [-2.26%, 0.71%] | -1.52% |
| 15m | 6h | 288 | 15.83% | 0.26% | 54.51% | [4.89%, 28.36%] | 33.96% |
| 15m | 1d | 224 | 32.69% | 0.92% | 55.80% | [0.48%, 79.23%] | 45.97% |
| 15m | resolution | 288 | 218.22% | 0.05% | 50.69% | [123.28%, 333.61%] | 266.77% |
| 1h | 1h | 288 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 288 | 15.32% | 0.11% | 51.74% | [5.13%, 27.49%] | 32.19% |
| 1h | 1d | 224 | 31.79% | 0.87% | 56.70% | [0.91%, 78.22%] | 39.55% |
| 1h | resolution | 288 | 240.85% | -0.25% | 47.57% | [131.18%, 377.85%] | 258.74% |

Without that market, resolution: 0s mean 195.95% (usd-weighted 264.17%, n=288); 1m mean 214.79% (usd-weighted 253.75%, n=288); 5m mean 214.99% (usd-weighted 258.32%, n=288); 1h mean 240.85% (usd-weighted 258.74%, n=288).

## Suspicious accounts

Accounts with `suspicious == true` in `data/suspicious.parquet`, flagged using fills before 2026-03-01. The full sample includes the winning bets that earned the flag.

236 accounts, 236 with an entry, 3823 entries, $5,222,318 insider usd.

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 3823 | 2.95% | -0.50% | 35.23% | [1.77%, 4.31%] | 4.83% |
| 0s | 6h | 3823 | 29.57% | -0.20% | 47.92% | [25.18%, 33.92%] | 35.47% |
| 0s | 1d | 2921 | 55.51% | 1.64% | 59.84% | [42.34%, 70.34%] | 36.70% |
| 0s | resolution | 3823 | 223.94% | 18.46% | 69.37% | [204.86%, 243.05%] | 188.35% |
| 30s | 1h | 3823 | 3.72% | -0.50% | 37.04% | [2.57%, 5.04%] | 5.99% |
| 30s | 6h | 3823 | 30.82% | -0.19% | 48.26% | [26.45%, 35.16%] | 37.91% |
| 30s | 1d | 2921 | 57.89% | 1.71% | 60.39% | [44.09%, 73.25%] | 38.73% |
| 30s | resolution | 3823 | 228.63% | 18.46% | 69.37% | [209.90%, 249.62%] | 192.72% |
| 1m | 1h | 3823 | 3.76% | -0.50% | 36.31% | [2.52%, 5.39%] | 5.58% |
| 1m | 6h | 3823 | 30.36% | -0.19% | 48.18% | [25.78%, 34.78%] | 37.04% |
| 1m | 1d | 2921 | 59.80% | 1.58% | 60.18% | [44.98%, 77.89%] | 39.13% |
| 1m | resolution | 3823 | 228.72% | 22.84% | 69.37% | [209.65%, 248.64%] | 191.93% |
| 5m | 1h | 3823 | 3.11% | -0.50% | 33.40% | [2.01%, 4.26%] | 4.90% |
| 5m | 6h | 3823 | 29.84% | -0.19% | 47.37% | [25.87%, 34.02%] | 37.55% |
| 5m | 1d | 2921 | 54.96% | 1.43% | 60.01% | [41.19%, 69.41%] | 36.46% |
| 5m | resolution | 3823 | 225.03% | 15.70% | 69.37% | [205.48%, 243.39%] | 190.75% |
| 15m | 1h | 3823 | 2.49% | -0.50% | 33.12% | [1.35%, 3.85%] | 4.15% |
| 15m | 6h | 3823 | 29.50% | -0.40% | 46.90% | [25.38%, 33.88%] | 36.89% |
| 15m | 1d | 2921 | 57.34% | 1.62% | 60.08% | [42.53%, 75.79%] | 37.65% |
| 15m | resolution | 3823 | 227.25% | 13.07% | 69.32% | [208.13%, 249.25%] | 192.64% |
| 1h | 1h | 3823 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 3823 | 26.01% | -0.50% | 43.40% | [22.37%, 29.83%] | 29.79% |
| 1h | 1d | 2921 | 47.46% | 1.23% | 58.68% | [35.60%, 59.83%] | 34.01% |
| 1h | resolution | 3820 | 218.94% | 10.56% | 65.55% | [200.69%, 239.38%] | 182.27% |

Resolution: 0s mean 223.94% (usd-weighted 188.35%, n=3823); 1m mean 228.72% (usd-weighted 191.93%, n=3823); 5m mean 225.03% (usd-weighted 190.75%, n=3823); 1h mean 218.94% (usd-weighted 182.27%, n=3820).

Price move from the entry print: 60s median 0.00%, mean -0.59%, mean price change -0.0008 (2834/3823 newer prints, 2059/3823 changed price); 5m median 0.00%, mean -0.25%, mean price change +0.0007 (3507/3823 newer prints, 2773/3823 changed price).

Leave-one-market-out drops the largest delay-0 resolution dollar PnL (US strikes Iran by February 28, 2026?, 765 entries, $6,209,736 of $9,836,063, 63% of dollar PnL).

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 3058 | 0.66% | -0.50% | 34.24% | [-0.27%, 1.84%] | 0.02% |
| 0s | 6h | 3058 | 11.90% | -0.30% | 46.80% | [8.61%, 15.82%] | 13.23% |
| 0s | 1d | 2455 | 45.24% | 1.15% | 58.21% | [29.81%, 62.01%] | 22.13% |
| 0s | resolution | 3058 | 163.92% | 3.00% | 63.44% | [142.70%, 187.68%] | 96.02% |
| 30s | 1h | 3058 | 1.42% | -0.50% | 35.28% | [0.40%, 2.52%] | 0.82% |
| 30s | 6h | 3058 | 12.74% | -0.24% | 46.89% | [9.45%, 16.67%] | 14.83% |
| 30s | 1d | 2455 | 47.91% | 1.15% | 58.82% | [31.42%, 67.25%] | 24.12% |
| 30s | resolution | 3058 | 168.67% | 2.90% | 63.44% | [146.84%, 193.21%] | 97.79% |
| 1m | 1h | 3058 | 1.68% | -0.50% | 35.02% | [0.48%, 3.28%] | 0.70% |
| 1m | 6h | 3058 | 12.85% | -0.30% | 46.86% | [9.03%, 16.89%] | 14.65% |
| 1m | 1d | 2455 | 49.69% | 1.12% | 58.45% | [32.15%, 70.43%] | 24.12% |
| 1m | resolution | 3058 | 169.46% | 2.90% | 63.44% | [146.18%, 195.38%] | 97.88% |
| 5m | 1h | 3058 | 1.01% | -0.50% | 32.01% | [0.14%, 1.94%] | 0.22% |
| 5m | 6h | 3058 | 12.21% | -0.39% | 45.45% | [8.66%, 15.69%] | 15.62% |
| 5m | 1d | 2455 | 44.01% | 1.12% | 58.33% | [30.47%, 58.89%] | 21.23% |
| 5m | resolution | 3058 | 164.76% | 2.90% | 63.44% | [143.85%, 188.45%] | 96.98% |
| 15m | 1h | 3058 | 0.76% | -0.50% | 30.51% | [-0.23%, 2.15%] | 0.32% |
| 15m | 6h | 3058 | 11.89% | -0.50% | 45.06% | [8.63%, 15.70%] | 15.47% |
| 15m | 1d | 2455 | 47.40% | 0.97% | 58.00% | [30.71%, 65.82%] | 22.92% |
| 15m | resolution | 3058 | 167.79% | 2.79% | 63.37% | [144.45%, 190.84%] | 99.65% |
| 1h | 1h | 3058 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 3058 | 9.44% | -0.50% | 43.00% | [6.86%, 12.31%] | 12.42% |
| 1h | 1d | 2455 | 37.16% | 0.93% | 56.54% | [24.65%, 50.76%] | 19.64% |
| 1h | resolution | 3055 | 159.91% | 2.58% | 60.56% | [139.70%, 183.75%] | 93.40% |

Without that market, resolution: 0s mean 163.92% (usd-weighted 96.02%, n=3058); 1m mean 169.46% (usd-weighted 97.88%, n=3058); 5m mean 164.76% (usd-weighted 96.98%, n=3058); 1h mean 159.91% (usd-weighted 93.40%, n=3055).

## Forward subset

Buys whose entry time is on or after 2026-03-01 by those same flagged accounts. The flag did not use these fills. A cluster that started before the split stays in the hindsight sample.

236 accounts, 60 with an entry, 555 entries, $1,089,789 insider usd.

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 555 | 1.11% | -0.50% | 35.50% | [-0.81%, 3.17%] | 0.42% |
| 0s | 6h | 555 | 15.81% | -0.50% | 40.54% | [2.56%, 31.40%] | 4.81% |
| 0s | 1d | 550 | 10.80% | -7.49% | 30.73% | [-3.37%, 29.02%] | 1.16% |
| 0s | resolution | 555 | 124.06% | -100.00% | 33.15% | [69.75%, 184.33%] | 44.11% |
| 30s | 1h | 555 | 1.49% | -0.50% | 35.50% | [-0.42%, 3.56%] | 0.37% |
| 30s | 6h | 555 | 15.86% | -0.50% | 40.36% | [3.41%, 29.49%] | 4.72% |
| 30s | 1d | 550 | 11.28% | -8.20% | 31.09% | [-4.04%, 29.17%] | 1.09% |
| 30s | resolution | 555 | 127.99% | -100.00% | 33.15% | [74.18%, 186.64%] | 38.02% |
| 1m | 1h | 555 | 1.17% | -0.50% | 34.77% | [-0.79%, 3.34%] | -0.70% |
| 1m | 6h | 555 | 15.38% | -0.50% | 38.56% | [2.41%, 30.83%] | 3.59% |
| 1m | 1d | 550 | 10.80% | -9.54% | 30.73% | [-3.68%, 29.13%] | 0.03% |
| 1m | resolution | 555 | 125.12% | -100.00% | 33.15% | [70.43%, 189.46%] | 38.56% |
| 5m | 1h | 555 | 0.82% | -0.50% | 34.95% | [-0.94%, 2.72%] | -1.24% |
| 5m | 6h | 555 | 13.60% | -0.50% | 38.74% | [2.11%, 26.71%] | 2.81% |
| 5m | 1d | 550 | 8.97% | -10.21% | 30.91% | [-4.94%, 27.46%] | -0.79% |
| 5m | resolution | 555 | 126.38% | -100.00% | 33.15% | [77.65%, 191.30%] | 35.50% |
| 15m | 1h | 555 | 0.98% | -0.50% | 33.69% | [-0.69%, 2.94%] | -0.91% |
| 15m | 6h | 555 | 12.60% | -0.50% | 37.12% | [2.38%, 25.65%] | 2.90% |
| 15m | 1d | 550 | 7.34% | -10.10% | 30.18% | [-6.03%, 22.95%] | -0.57% |
| 15m | resolution | 555 | 126.77% | -100.00% | 33.15% | [71.99%, 191.26%] | 36.29% |
| 1h | 1h | 555 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 555 | 5.51% | -0.50% | 38.74% | [-0.41%, 13.86%] | 1.44% |
| 1h | 1d | 550 | 0.95% | -9.13% | 30.55% | [-8.80%, 13.32%] | -1.71% |
| 1h | resolution | 555 | 115.41% | -100.00% | 33.15% | [67.39%, 174.05%] | 36.30% |

Resolution: 0s mean 124.06% (usd-weighted 44.11%, n=555); 1m mean 125.12% (usd-weighted 38.56%, n=555); 5m mean 126.38% (usd-weighted 35.50%, n=555); 1h mean 115.41% (usd-weighted 36.30%, n=555).

Price move from the entry print: 60s median 0.00%, mean 0.17%, mean price change -0.0007 (425/555 newer prints, 343/555 changed price); 5m median 0.00%, mean 0.44%, mean price change -0.0003 (528/555 newer prints, 426/555 changed price).

Leave-one-market-out drops the largest delay-0 resolution dollar PnL (US x Iran ceasefire by April 15?, 60 entries, $479,736 of $480,747, 100% of dollar PnL). The largest equal-weight sum of returns at that cell is US x Iran ceasefire by April 7?.

| delay | horizon | n | mean | median | win rate | 95% CI | usd-weighted |
|---|---|---:|---:|---:|---:|---|---:|
| 0s | 1h | 495 | 0.62% | -0.50% | 34.14% | [-1.44%, 2.93%] | -0.01% |
| 0s | 6h | 495 | 16.59% | -0.50% | 39.80% | [3.16%, 34.48%] | 3.40% |
| 0s | 1d | 492 | 11.55% | -9.85% | 29.07% | [-5.94%, 31.70%] | -0.08% |
| 0s | resolution | 495 | 81.66% | -100.00% | 26.67% | [27.40%, 140.29%] | 0.11% |
| 30s | 1h | 495 | 1.09% | -0.50% | 33.74% | [-1.02%, 3.35%] | 0.19% |
| 30s | 6h | 495 | 16.66% | -0.50% | 39.60% | [3.12%, 34.54%] | 3.58% |
| 30s | 1d | 492 | 11.98% | -10.85% | 29.47% | [-4.69%, 31.39%] | 0.03% |
| 30s | resolution | 495 | 85.31% | -100.00% | 26.67% | [30.85%, 153.31%] | -6.74% |
| 1m | 1h | 495 | 0.83% | -0.50% | 33.13% | [-1.27%, 3.15%] | -0.95% |
| 1m | 6h | 495 | 16.23% | -0.50% | 37.98% | [2.05%, 34.72%] | 2.37% |
| 1m | 1d | 492 | 11.52% | -10.65% | 29.07% | [-4.81%, 31.83%] | -1.09% |
| 1m | resolution | 495 | 82.63% | -100.00% | 26.67% | [26.85%, 143.31%] | -5.38% |
| 5m | 1h | 495 | 0.48% | -0.50% | 33.74% | [-1.57%, 2.52%] | -1.13% |
| 5m | 6h | 495 | 14.29% | -0.50% | 38.59% | [2.07%, 29.96%] | 1.95% |
| 5m | 1d | 492 | 9.50% | -11.60% | 30.08% | [-5.21%, 28.78%] | -1.46% |
| 5m | resolution | 495 | 84.36% | -100.00% | 26.67% | [28.78%, 155.77%] | -6.97% |
| 15m | 1h | 495 | 0.77% | -0.50% | 33.13% | [-1.20%, 2.87%] | -0.86% |
| 15m | 6h | 495 | 13.28% | -0.50% | 36.77% | [1.83%, 29.66%] | 1.94% |
| 15m | 1d | 492 | 7.76% | -11.55% | 29.27% | [-7.02%, 25.41%] | -1.38% |
| 15m | resolution | 495 | 85.54% | -100.00% | 26.67% | [25.29%, 152.70%] | -5.73% |
| 1h | 1h | 495 | -0.50% | -0.50% | 0.00% | [-0.50%, -0.50%] | -0.50% |
| 1h | 6h | 495 | 5.85% | -0.50% | 38.59% | [-0.28%, 14.58%] | 0.28% |
| 1h | 1d | 492 | 0.93% | -9.76% | 30.49% | [-9.32%, 16.26%] | -3.07% |
| 1h | resolution | 495 | 74.71% | -100.00% | 26.67% | [17.76%, 136.33%] | -6.24% |

Without that market, resolution: 0s mean 81.66% (usd-weighted 0.11%, n=495); 1m mean 82.63% (usd-weighted -5.38%, n=495); 5m mean 84.36% (usd-weighted -6.97%, n=495); 1h mean 74.71% (usd-weighted -6.24%, n=495).

## Caveats

The suspicious-account table is hindsight-biased: those accounts were flagged because a pre-split bet won. The forward subset is the copy a discovery rule could have placed after the split.

Bootstrap draws treat entries as independent. Entries in the same market move together, so the interval is tight relative to market-level uncertainty. The leave-one-market-out table is the check for one market carrying the mean.

Slippage is charged on the entry only. Resolution pays exactly 0 or 1. Prints whose outcome is outside that market's two listed outcomes are omitted from the tape.
