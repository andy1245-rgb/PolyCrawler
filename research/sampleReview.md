# Manual review: 20 random flagged accounts

Sample: 20 accounts drawn with `seed=7` from the 236 flagged by discovery step 1 (`data/suspicious.parquet`), excluding the 9 labeled wallets. Each account was reviewed from its own activity history (`data/raw/activity/`, capped at about 30 markets) plus our fill data.

**Every sampled account was flagged on the Iran strike ladder** ("US strikes Iran by Feb 28 / Mar 1 / ..."), because step 1 has only run on `configs/insiderCases.yaml`. The verdicts below therefore say nothing about other event types.

## Verdicts

| # | Account | Verdict | Why |
|---|---|---|---|
| 11 | cokelight `0xf1d5…` | **Insider (cluster)** | Created Feb 22. Bought No at 0.98 on daily dates, then Feb 28 Yes. Trades in the same second as the Lettucehead718 group. |
| 12 | gulligan784 `0xa34d…` | **Insider (cluster)** | Same pattern; same-second fills with wannabesedated and suffix-295. |
| 18 | wannabesedated `0xf37a…` | **Insider (cluster)** | Same pattern; first Feb 28 Yes buy came 8s after Lettucehead718's. |
| 19 | DimBull `0xc029…` | **Insider (cluster)** | Same pattern; 9 same-second fills with suffix-295 and 6 three-way with Lettucehead718 + suffix-295. |
| 14 | Neodbs `0x56ef…` | **Likely insider** | One trade ever: $9.9k Yes at 0.10, about 35h before resolution. |
| 17 | jamesjohnson176 `0x9c6b…` | **Likely insider** | One trade ever: $8.5k Yes at 0.22 on Feb 28 05:29 UTC, about 1.5h before the price jumped. |
| 6 | `0x0ad7…` | **Likely insider** | Fresh account. Bought Feb 28 Yes plus Khamenei-out and Israel-strike Yes, all within 36h of the strike. |
| 13 | baravvv `0x9771…` | **Likely insider** | Fresh, 2 markets. Feb 28 Yes 19h before; Khamenei Yes the day after. |
| 10 | doitnowdo `0xe8cc…` | Possible | Fresh, 2 markets, but entered 10 days early and put more on "by March 31" at 0.59. That looks like conviction, not a known date. |
| 7 | `0x17a5…` | Possible | Fresh, 3 markets. Bought Mar 1 / Mar 5 Yes and Feb 27 No at 0.96: knew "soon, but not by the 27th". |
| 4 | `0x28b7…` | Possible | Fresh. Bought Feb 28 / Mar 1 / Mar 2 / Mar 3 within the same minute, 4.5 days early: a range bet. |
| 1 | latinalover77 `0x6732…` | Possible | Fresh, $34k spread over Mar 1–3, with Feb 28 a small piece. Sold early for profit. |
| 16 | lishengshun `0x9431…` | Speculator | Lost the Feb 22 and Feb 23 dates first, then won on Feb 28 eight days out. |
| 2 | `0x8517…` | Speculator | Sprayed $0.02–0.03 Yes on Feb 25, 26, 27 and 28 ("next strike on" dates), then larger on Feb 28. |
| 3 | `0xec8f…` | Speculator | Bought every date from Feb 21 to Mar 7, 9 days early. |
| 15 | `0x435e…` | Speculator | Bought Feb 23–27 (all lost) plus Mar 1, 2 and 8. |
| 8 | `0xb7f6…` | Speculator | Bought Feb 1, Feb 9 and Feb 22 (all lost); the Feb 28 win came 24 days early. |
| 9 | 6FigsPlz `0xc5df…` | Speculator | Lost several dates; also bet on Starmer. |
| 20 | platmagic97 `0x6539…` | Speculator | Also bet on the Super Bowl and the MVP; the Iran win came 10 days early. |
| 5 | `0x37a4…` | Speculator | $3k total, including the Lakers and GTA 6: a recreational account. |

**Tally:** 8 insider or likely insider (4 of them in one coordinated cluster), 4 possible, 8 speculators. Precision of the current step 1 rule is roughly **40–60%** on this event.

## The six-wallet cluster

Bubblemaps reported 6 fresh wallets funded through similar paths. The fills show these six accounts trading the same outcome in the **same second** repeatedly from Feb 23 to Feb 28:

| Pair | Same-second fills |
|---|---:|
| DimBull + suffix-295 | 9 |
| Lettucehead718 + suffix-295 | 9 |
| DimBull + Lettucehead718 + suffix-295 | 6 |
| gulligan784 + wannabesedated | 4 |
| Lettucehead718 + wannabesedated | 3 |

All were created around Feb 22. Their first "US strikes Iran by Feb 28" Yes buys were at 20:49:57 (DimBull), 21:09:49 (suffix-295), 21:09:53 (Lettucehead718), 21:09:57 (wannabesedated), 21:19:47 (gulligan784) and 23:41:59 (cokelight) on Feb 27. **Co-trading recovers the cluster without any funding data.** It is not provable from this alone, but it is very strong.

## What this means for discovery

1. **Co-trading is the best cluster link we have**: it's free (no API calls) and it found the Bubblemaps cluster that Polygon funding data couldn't.
2. **Spray versus precise.** Speculators buy many dates on a ladder and lose the early ones; insiders put most of their money on the right date. Add a feature: the share of the account's USD in that event that went to the winning market, and the number of losing ladder dates before the win.
3. **Concentration and one-shot accounts** (1–2 markets, one large ticket) were the cleanest insiders.
4. **Recreational noise:** sports and gaming bets mixed in are a speculator tell.
5. **Timing:** insiders entered 4–36h before resolution; speculators often 8–24 days early. Consider a maximum lead time, but measure it per event type; for the Iran strike it was hours.
