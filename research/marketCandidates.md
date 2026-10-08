# Polymarket insider-case market candidates

Pulled 2026-10-08 from public Gamma and Data APIs (no key). Wallet rows are in `knownWallets.csv`. Gamma `endDate` on grouped markets is often the group end, not the date in the question; contract dates below are the dates in the question. Data API `activity` returns TRADE, REDEEM, REWARD, YIELD. It does not return deposits, so parent funding wallets could not be recovered.

## 1. US strikes Iran by February 28, 2026

Event `us-strikes-iran-by` ("US strikes Iran by...?") is closed. Event volume about **$529.0M**, **65** markets. Contracts dated before 28 Feb 2026 resolved **No**. The 28 Feb contract and later dated contracts in this group resolved **Yes**.

| Question | conditionId | Volume | Winner |
|---|---|---:|---|
| US strikes Iran by February 28, 2026? | `0x3488f31e6449f9803f99a8b5dd232c7ad883637f1c86e6953305a2ef19c77f20` | $89.7M | Yes |
| US strikes Iran by February 27, 2026? | `0x09cbe3e796661a1d820580145488ad2ccb9ad1e720efcd64b448bb77b97007c1` | $25.1M | No |
| US strikes Iran by January 31, 2026? | `0xabb86b080e9858dcb3f46954010e49b6f539c20036856c7f999395bfd58d01e6` | $41.8M | No |
| US strikes Iran by March 31, 2026? | `0x4b02efe53e631ada84681303fd66d79ad615f3d2b6a28b4633d43d935f89af58` | $22.2M | Yes |
| US strikes Iran by March 1, 2026? | `0x15aa3c1259a716915e068a0d63c3885d2301d29e8982cbb1717ecb9b63d02d95` | $8.1M | Yes |

Sibling events on the same episode:

| Event slug | Question family | Event volume | What resolved |
|---|---|---:|---|
| `us-next-strikes-iran-on-843` | US next strikes Iran on...? | $56.6M | Only **28 Feb 2026** Yes ($5.8M). Earlier February days No. |
| `usisrael-strikes-iran-by` | US or Israel strike Iran by...? | $19.8M | 28 Feb 2026 Yes ($5.9M). 31 Jan and 15 Feb No. |
| `khamenei-out-as-supreme-leader-of-iran-by-february-28` | single market | $131.1M | **Yes**. conditionId `0xd4bbf7f6707c67beb736135ad32a41f6db41f8ae52d3ac4919650de9eeb94ed8` |
| `khamenei-out-as-supreme-leader-of-iran-by-march-31` | single market | $63.2M | **Yes**. `0x70909f0ba8256a89c301da58812ae47203df54957a07c7f8b10235e877ad63c2` |
| `us-x-iran-ceasefire-by` | ceasefire by date | $280.1M | 31 Mar No ($44.4M). 7 Apr Yes ($173.7M). 15 Apr Yes. |
| `will-the-iranian-regime-fall-by-march-31` | single market | $63.2M | **No**. `0x61ce3773237a948584e422de72265f937034af418a8b703e3a860ea62e59ff36` |

**Wallets (news-named, addresses resolved from the Feb 28 trade tape).** Suggested `splitDate`: **2026-02-28**. Cluster accounts start appearing 15–28 Feb.

| Wallet | Name on the tape | Created | Markets | Buy USD | Feb 28 Yes | Won |
|---|---|---|---:|---:|---|---|
| `0x6f53691020762651d14e5a543519e14d5c8654fd` | Lettucehead718 | 2026-02-22 | 10 | 68,899 | redeem ~$58k | yes |
| `0xb390ae2cc3fd8cb2670a62129faeb775faee106c` | suffix-295 | 2026-02-22 | 10 | 62,624 | redeem ~$52k | yes |
| `0x1caa6a7ad0c6916aef7b67946de2e57ad24846a0` | Careless-Bug | 2026-02-25 | 15 | 230,941 | ~$61k at 0.112, redeem ~$561k | yes |
| `0xa4eb52229991c074bc560f825bf2776d77acd010` | Wet-Film (name now `djijaij83jdo4jdlwjflsg`) | 2026-02-28 | 7 | 116,177 | ~$7.6k at 0.19, redeem ~$40k | yes |
| `0xca886a7ed635c3b770fccfd251c86eec34967caa` | Courteous-Epoch / Mdb2303 | 2026-01-09 | 143 | 66,526 | ~$6.4k at 0.19, unsold | yes |
| `0x9c274a7dfe8829cc8e178b27e3ff5eb7bdb5d050` | Aware-Initialize | 2026-01-27 | 59 | 164,913 | redeem ~$24k | yes |

Lettucehead718 and suffix-295 share timestamps (No sells at `2026-02-27 00:13:44Z`, Yes buys at `2026-02-28 06:57:53Z`). That is the Bubblemaps pair. Their book is a ladder: buy No on 22–26 Feb (those resolved No) and Yes on 28 Feb. They were created six days before the strike, not inside 24 hours. Wet-Film was created 7 minutes before its first trade. Roeyha2026 / Gargantuan-Scenery and Sunny-Corduroy did not appear on ≥$200 trades in this market from 19–28 Feb. A different account, `cb10` / Gargantuan-Math (`0xe352e07e33fe2dd0ac90569c3687341bf6cf4adf`), was buying No and is not the same name.

**Not labeled.** Two more accounts match the fresh low-price win but have more than 5 markets, so they are not in the CSV:

- `0x607fec58640fcea5cb837adb09d658747720592c` whopperlover / Lavish-Majority, created 2026-02-15, 14 markets, ~$67k Yes at 0.141, redeem ~$312k on Feb 28.
- `0x514550b8f94f24e3bd5fca1c8af19e985fb71f46` 65154861 / Long-Term-Formation, created 2026-02-13, 15 markets, ~$57k Yes at 0.174, redeem ~$337k.

The largest sub-0.40 Yes buyers (Magamyman, ScottyNooo, CasualFox99) are 2024–2025 accounts. They are not fresh.

## 2. Bubblemaps wallet `0x09d3273fa76282ce09f4f35a87d6f087c05f4e84`

Name **fuego66**, pseudonym Those-Outrage. Profile created **2026-02-15**. 11 markets, $88,226 bought, first trade 2026-02-15. Main position: **$56,250** Yes on "US strikes Iran by February 28, 2026?" at avg **0.142**, redeem **$362,607**. Also $1,950 Yes at 0.15 on "US or Israel strike Iran by February 28?" (redeem $13,000) and smaller Yes on Feb 20, Feb 27, and regime-fall markets, plus bitcoin dips. This is one cluster member, not a $2.4M book by itself. Same-market overlap with Lettucehead, Careless-Bug, Wet-Film, and the two unlabeled accounts above is the cluster signal. No other of the nine wallets was published, and deposits are not in this API.

## 3. June 2025 US / Israel strikes

| Event slug | Event volume | Resolution |
|---|---:|---|
| `israel-strike-on-iran-on` | $10.8M | Daily "Israel strike on Iran" **14–24 Jun 2025 Yes**, **25–30 Jun No**. |
| `us-strikes-iran-on-526` | $0.30M | "US strike on Iran" **22–30 Jun 2025 all No**. |

June 2025 is a real resolved ladder, but the US-strike book is thin and the Feb 2026 names were not active then. Use it as an earlier control, not as the insider sample.

## 4. Maduro / Venezuela, January 2026

Operation window is early January 2026. Buys that match the reported size landed **31 Dec 2025–2 Jan 2026**. Suggested `splitDate`: **2026-01-03**.

| Event slug | Market | conditionId | Volume | Winner |
|---|---|---|---:|---|
| `maduro-out-in-2025` | Maduro out by January 31, 2026? | `0x580adc1327de9bf7c179ef5aaffa3377bb5cb252b7d6390b027172d43fd6f993` | $11.0M | Yes |
| `maduro-out-in-2025` | Maduro out in 2025? | `0xafc235557ace53ff0b0d2e93392314a7c3f3daab26a79050e985c11282f66df7` | $34.6M | No |
| `maduro-out-in-2025` | Maduro out by March 31, 2026? | `0x18d8c59309811ce5618ea941f9bde2a96afa5d876a69c42fba2da4bcc56d3c5e` | $3.8M | Yes |
| `us-forces-in-venezuela-by` | US forces in Venezuela by January 31, 2026? | `0xbb8bfdef9052b2709557a6f8f28b23551e3134bfb86eca800211e2191703ee65` | $6.4M | Yes |
| `will-the-us-invade-venezuela-in-2025` | Will the U.S. invade Venezuela by January 31, 2026? | `0x7f3c6b9029a1a4a932509c147a2cc0762e1116b7a4568cde472908b29dd4889d` | $8.4M | No |
| `us-operation-to-capture-maduro-in-2025` | U.S. operation to capture Maduro in 2025? | `0x69ac865d7824f22808d29deec2ed5090eaeeb27094e6936970c4b4c5660a87d5` | $0.12M | No |

Event volumes: Maduro-out ladder **$56.6M** (closed), US forces in Venezuela **$9.4M** (closed), invade ladder **$14.2M** (event still open; the 31 Jan market is closed).

**Inferred wallets** (not named in the source note; pattern is fresh ≤14 days, ≤5 markets, Yes ≤0.30, ≥$1,000, won):

| Wallet | Pseudonym | Created | Markets | Buy | Price | Redeem | Fit |
|---|---|---|---:|---:|---:|---:|---|
| `0x31a56e9e690c621ed21de08cb559e9524cdb8ed9` | Burdensome-Mix | 2025-12-26 | 4 | $32,538 on this market | 0.075 | $436,760 | Matches the reported ~$33k → ~$410k profit (here ~$404k). First trade 2025-12-27. |
| `0xa72db1749e9ac2379d49a3c12708325ed17febd4` | Wee-Pseudoscience | 2025-12-24 | 1 | $5,783 | 0.072 | $80,765 | Same market, 2026-01-02, one trade. |

No other ≥$5k sub-0.20 Yes buyer on that market was in the $30k band. The news writeup did not publish an address; these are pattern matches.

## 5. ACDC prefixes `0x88e6...` and `0xc0a...`

Top holders (50–100 per outcome) on the Feb 28 strike, Khamenei 28 Feb, Khamenei 31 Mar, regime-fall 31 Mar, Maduro 31 Jan, and the d4vd Google market contained **no `0x88e6` address**.

One `0xc0a` holder: `0xc0a1298e2d6ba216efb554865369152da9c5a33b` (EddyAncogld / United-Bass) on the Iran ceasefire book. Profile created 2025-12-21, **92 markets**, about $2.5M bought, mostly at **0.83–0.98**. That fails the fresh longshot pattern, so it is not treated as an ACDC ground-truth wallet. The 152-address list is not recoverable from prefixes plus top-holder scans.

## 6. Russia–Ukraine battlefield

Resolved ladders found by slug (a fuzzy search for "will russia capture" returned 47 events, only 5 closed, and **missed Pokrovsk**):

| Event slug | Volume | Shape |
|---|---:|---|
| `will-russia-capture-pokrovsk-by` | $4.0M | 5 markets. Mar 31 No, Jun 30 No, Aug 31 Yes ($1.8M), Oct 31 Yes, Dec 31 Yes. |
| `will-russia-capture-kostyantynivka-by` | $10.0M | 17 markets, mixed Yes/No. |
| `will-russia-capture-all-of-pokrovsk-by` | $0.32M | Apr 30 2026 No, May 31 2026 Yes. |
| `will-russia-capture-toretske-by` | $0.16M | small, mostly thin markets. |

No closed "Will Russia capture Myrnohrad by...?" event. The open event `will-ukraine-re-enter-myrnohrad-by-may-31` is about $0.13M. Ukraine ceasefire ladders (`russia-x-ukraine-ceasefire-by-...`) are numerous and mostly already closed **without** a confirmed insider wallet; they are a negative control, not a label source.

On "Will Russia capture Pokrovsk by August 31?" the ≥$500 tape (May–Aug 2025, 321 trades) had about **$11k** of Yes buys at ≤0.30 and ≥$1k, spread across small tickets. No fresh-account whale and no 14-win account turned up. Battlefield markets are a weak fit for a funding-cluster detector: the suspected edge is ISW map latency, volume is an order of magnitude below Iran, and most town markets are still open.

## 7. Nobel 2025 and Google Year in Search 2025

| Event slug | Event volume | Resolved winner | Market volume |
|---|---:|---|---:|
| `nobel-peace-prize-winner-2025` | $21.5M | María Corina Machado Yes. End 2025-10-10. conditionId `0x14a3dfeba8b22a32feb0f10763db68bc4d2abeb5bff90e9ae20de53793b35a1d` | $2.24M |
| `1-searched-person-on-google-this-year` | $57.1M | **d4vd** Yes. conditionId `0xea17b1284d10617a57f910b2ea63bdef481b1724a4b899d454ff104bea67b657` | $14.0M |
| `top-5-most-searched-people-on-google-2025` | $10.6M | Yes on Pope Leo XIV, Jimmy Kimmel, Kendrick Lamar, and others | — |
| `1-searched-actor-on-google-this-year` | $3.8M | Mikey Madison Yes | $0.31M |
| `1-searched-passings-on-google-this-year` | $7.2M | Charlie Kirk Yes | $0.34M |
| `1-searched-tv-show-on-google-this-year` | $0.42M | "Other" Yes at ~$0 volume | — |

Nobel ≥$1k tape: one Yes buy at 0.10 for **$1,500** on 9 Oct (`0xa430506774f9efaf39903ee7e0db1351f66891ca`). No fresh cluster. Google d4vd ≥$500 tape: largest sub-0.25 Yes buyer was **$7.3k at 0.064**, and that account (`0xee50a31c3f5a7c77824b12a941a54388a2827ed6`, 0xafEe) was created in **2024** and was mostly buying favorites (Trump, Pope, Bianca) at 0.56–0.97. Interesting one-shot markets, not ground-truth wallet labels.

## Recommendation

Ranked for a backtest that needs insider-like wallets, volume, and a before/after date:

1. **Iran military (use this).** One episode with a sharp `splitDate` of **2026-02-28**, plus dated markets on both sides (Jan–Feb Nos, Feb 28 and March Yes) and related books (Khamenei $131M, ceasefire $280M, strike ladder $529M). Seven news-named wallets with full addresses. Sample is one crisis, not a long panel, but it is the only set with both size and labels. The ≤5-market freshness rule **misses** this cluster: labeled accounts traded 7–143 markets (the tight ones are 7–15). A cap of about 15 markets, or "most USDC in one event," fits the tape better than ≤5.
2. **Venezuela (use as the clean label check).** Two wallets actually meet fresh ≤14 days, ≤5 markets, Yes ≤0.30, ≥$1k, and won. The larger one matches the reported ~$33k size. Volume is real (Maduro-out event $57M, plus forces and invade markets) but it is **one operation**. Good for validating the detector, too small for a stable copy-trading backtest. `splitDate` **2026-01-03**.
3. **Ukraine battlefield (do not use as insider labels).** A few resolved town ladders exist (Pokrovsk $4M, Kostyantynivka $10M) and ceasefire markets are already closed, so a price panel is possible. We found no fresh longshot winner and not the 14-win account. Most capture markets are still open. The suspected behavior is map-update front-running, which this funding-cluster detector is not built for.
4. **Nobel and Google (skip as labels).** Single announcements. No wallet met the fresh-account rule. d4vd is the only large longshot resolution ($14M) and is a reasonable negative control.

```yaml
eventSlugs:
  iranMilitary:
    - us-strikes-iran-by
    - us-next-strikes-iran-on-843
    - usisrael-strikes-iran-by
    - khamenei-out-as-supreme-leader-of-iran-by-february-28
    - khamenei-out-as-supreme-leader-of-iran-by-march-31
    - us-x-iran-ceasefire-by
    - will-the-iranian-regime-fall-by-march-31
    - israel-strike-on-iran-on
  venezuela:
    - maduro-out-in-2025
    - us-forces-in-venezuela-by
    - will-the-us-invade-venezuela-in-2025
    - trump-invokes-war-powers-against-venezuela-by
    - us-operation-to-capture-maduro-in-2025
  ukraineBattlefield:
    - will-russia-capture-pokrovsk-by
    - will-russia-capture-kostyantynivka-by
    - will-russia-capture-all-of-pokrovsk-by
  other:
    - nobel-peace-prize-winner-2025
    - 1-searched-person-on-google-this-year
    - top-5-most-searched-people-on-google-2025
splitDate:
  iranMilitary: "2026-02-28"
  venezuela: "2026-01-03"
```
