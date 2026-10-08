# Event universe for rolling copy tests

Pulled 2026-10-08 from the keyless Gamma API. This set is the events to add on top of `configs/insiderCases.yaml`. It does not repeat that file's Iran (Feb 2026) or Venezuela (Jan 2026) slugs.

## Method

Tags came from `GET /tags?limit=100&offset=N` (about 5,000 tags). Closed events came from `GET /events?tag_slug=&closed=true&order=volume&ascending=false&limit=100&offset=N`, paged until a page's smallest event was under $1M. Named cases that tags missed (Swift, ZachXBT/Axiom, Biden, OpenAI browser, Beast Games) were found with `GET /public-search`. Requests slept 0.2s.

The date filter uses Gamma `closedTime` (when the event resolved), from 2024-06-01 through 2026-10-01. On grouped markets, `endDate` is often a placeholder after the real resolution. The `endDate` column below is `closedTime`.

Floor is $1M event volume. Three documented cases sit under that floor and are included anyway: Nasrallah ($0.76M), Beast Games season 1 ($0.97M), Taylor Swift engagement ($0.39M). Sports, weather, crypto price markets, tweet-count markets, and market-cap ladders are out. Pure election outcomes are out except three controls.

Fill estimate uses the smaller-event ratio in `research/marketCandidates.md` (~$57M → 215k fills), which is a bit higher than the Iran-strike ratio (~$529M → 1.9M fills). Estimated fills = volume × 215,000 / 57,000,000. The Iran-strike ratio would put this set at about 5.48M fills instead of 5.76M. Nothing here is estimated above 3M fills (that line is about $800M of volume). The largest new event is the TikTok ban, about 451k fills.

Same-episode markets were collapsed. Not added, because they are the Feb–Jun 2026 Iran war already represented by `us-x-iran-ceasefire-by` and `us-strikes-iran-by`: `us-x-iran-permanent-peace-deal-by` ($479M), `us-forces-enter-iran-by` ($367M), `us-x-iran-ceasefire-extended-by` ($210M), the Hormuz traffic ladders, and the later "regime fall by April/May/June" markets. June 2025 siblings of `israel-strike-on-iran-on` (Fordow, "US military action before July", "ceasefire before July") were also left out. FOMC meetings larger than the March 2025 control were left out so the control does not dominate the fetch: January 2025 ($191M), May ($88M), June ($107M), July ($137M), September 2025 ($221M), December 2025 ($394M), January 2026 ($660M), April 2026 ($284M). `presidential-election-winner-2024` is $3.69B (on the order of 14M fills) and is not included. `nobel-peace-prize-2025` (Trump/Musk yes-no, $30.8M) is the same morning as the winner field and is not included.

North Korea, the Hezbollah pager claim, Sinwar's death, Sora's public release, and Apple keynote-mention markets were closed but under $1M.

These slugs are not 72 independent shocks. The Russia–Ukraine ceasefire rows are checkpoints of one diplomatic process. The two Taiwan-invasion rows are the same question at two deadlines. Yoon's removal and his later prison sentence are one saga. Spotify, Google, the Game Awards, and Time's 2025 Person of the Year all resolve in the first half of December 2025. The Mexico anti-cartel market closes in the same fortnight as the Maduro operation already in `insiderCases.yaml`.

## Totals

72 events. Volume $1,526.3M. Estimated fills 5.76M (conservative ratio) or 5.48M (Iran-strike ratio). Largest single event: TikTok ban, ~451k fills. No event flagged above 3M fills.

| Category | Events | Volume | Est. fills |
|---|---:|---:|---:|
| Military strikes | 9 | $120.7M | 455k |
| Ceasefires and diplomacy | 9 | $181.9M | 686k |
| Leaders and territory | 8 | $189.1M | 713k |
| Ukraine battlefield | 3 | $19.1M | 72k |
| Awards and rankings | 11 | $332.0M | 1,252k |
| Policy announcements | 5 | $198.2M | 748k |
| Tech and product launches | 8 | $59.9M | 226k |
| Entertainment | 4 | $88.9M | 335k |
| Investigation announcement | 1 | $39.7M | 150k |
| Appointments | 5 | $100.5M | 379k |
| Courts | 3 | $22.2M | 84k |
| Fed control | 3 | $139.6M | 527k |
| Election control | 3 | $34.6M | 131k |
| **Total** | **72** | **$1,526.3M** | **5,758k** |

| Quarter (by closedTime) | Events | Volume | Est. fills |
|---|---:|---:|---:|
| 2024Q3 | 3 | $24.7M | 93k |
| 2024Q4 | 11 | $222.7M | 840k |
| 2025Q1 | 8 | $234.5M | 885k |
| 2025Q2 | 5 | $76.6M | 289k |
| 2025Q3 | 12 | $94.7M | 357k |
| 2025Q4 | 13 | $375.7M | 1,417k |
| 2026Q1 | 12 | $352.9M | 1,331k |
| 2026Q2 | 4 | $113.8M | 429k |
| 2026Q3 | 4 | $30.7M | 116k |

2024Q3 is thin because non-election books were still small. 2025Q4 and 2026Q1 are heavy because several embargoed lists drop in December and the ZachXBT, Stranger Things, and Mexico markets resolve in January–February.

## Military strikes

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `nasrallah-remains-leader-of-hezbollah-through-october-31` | Nasrallah remains Hezbollah leader through Oct 31? | 2024-09-28 | $0.76M | 3k | Strike timing. Under the $1M floor; included as the September 2024 killing. | — |
| `will-israel-invade-lebanon-in-september` | Will Israel invade Lebanon in September? | 2024-10-08 | $13.8M | 52k | Ground invasion. Same Hezbollah war as Nasrallah, different fact. | — |
| `israel-strike-on-iranian-nuclear-facility-in-2024` | Israel strike on Iranian nuclear facility in 2024? | 2024-11-19 | $10.1M | 38k | Oct 2024 Israel–Iran strike. Separate from June 2025 and Feb 2026. | — |
| `will-israel-invade-syria-in-2024` | Will Israel invade Syria in 2024? | 2024-12-21 | $16.8M | 63k | Israel move into Syria as the regime collapsed. | — |
| `pakistan-military-strike-on-india-by-friday` | Pakistan military strike on India by Friday? | 2025-05-10 | $17.1M | 65k | May 2025 strike deadline. | — |
| `thailand-strikes-cambodia-by-friday` | Thailand strikes Cambodia by Friday? | 2025-07-31 | $15.0M | 57k | July 2025 border strike. | — |
| `houthi-strike-on-israel-by-august-31` | Houthi strike on Israel by August 31? | 2025-08-28 | $13.3M | 50k | Strike-by-date. | — |
| `us-strikes-yemen-by-september-30` | US strikes Yemen by...? | 2026-01-05 | $3.5M | 13k | Small date ladder, resolved January 2026. | — |
| `us-anti-cartel-ground-operation-in-mexico-by-january-31` | U.S. anti-cartel ground operation in Mexico by January 31? | 2026-02-04 | $30.2M | 114k | Different country from Maduro, same fortnight. Treat as possibly correlated with the Venezuela book. | — |

## Ceasefires and diplomacy

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `israel-x-hezbollah-ceasefire-in-2024` | Israel x Hezbollah Ceasefire in 2024? | 2024-12-05 | $40.1M | 151k | Negotiated deal; the parties know before the announcement. Follows the September war, it is not the same contract. | — |
| `russia-x-ukraine-ceasefire-in-2024` | Russia x Ukraine Ceasefire in 2024? | 2025-01-01 | $3.5M | 13k | One checkpoint of the Ukraine ceasefire series. | — |
| `trump-x-ukraine-mineral-deal-signed-before-may` | Trump x Ukraine mineral deal signed before May? | 2025-05-04 | $6.8M | 26k | Signing. Both governments can know. | — |
| `russia-x-ukraine-ceasefire-before-july` | Russia x Ukraine ceasefire before July? | 2025-07-01 | $17.1M | 65k | Same ceasefire series. | — |
| `israel-x-hamas-ceasefire-before-august` | Israel x Hamas ceasefire before August? | 2025-08-01 | $11.2M | 42k | Gaza deadline before the October deal. | — |
| `russia-x-ukraine-ceasefire-before-october` | Russia x Ukraine ceasefire before October? | 2025-10-01 | $8.8M | 33k | Same ceasefire series. | — |
| `when-will-israel-announce-ceasefire` | When will Israel announce ceasefire? | 2025-10-13 | $11.2M | 42k | Daily ladder for the October 2025 Gaza announcement. | — |
| `russia-x-ukraine-ceasefire-in-2025` | Russia x Ukraine ceasefire in 2025? | 2026-01-01 | $73.8M | 278k | Year-end checkpoint. Largest row in this series; later $141M and $61M rungs were left out so one series does not dominate. | — |
| `russia-x-ukraine-ceasefire-by-april-30-2026` | Russia x Ukraine ceasefire by April 30, 2026? | 2026-05-01 | $9.5M | 36k | Same ceasefire series, spring 2026 checkpoint. | — |

## Leaders and territory

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `will-assad-remain-president-of-syria-through-2024` | Will Assad remain President of Syria through 2024? | 2024-12-08 | $7.6M | 29k | Exit from Damascus. The inner circle can know before the public. | — |
| `yoon-out-as-president-of-south-korea-before-april` | Yoon out as president of South Korea before April? | 2025-04-01 | $32.4M | 122k | Removal date. Court vote is a separate row under courts. | — |
| `zelenskyy-out-as-ukraine-president-before-july` | Zelenskyy out as Ukraine president before July? | 2025-07-01 | $3.5M | 13k | Leader-exit deadline. Weak if it resolves No. | — |
| `xi-jinping-out-in-2025` | Xi Jinping out in 2025? | 2026-01-01 | $78.7M | 297k | Leader-exit by year end. Large, and a low base rate. | — |
| `will-china-invade-taiwan-in-2025` | Will China invade Taiwan in 2025? | 2026-01-01 | $12.4M | 47k | Invasion deadline. Pair with the June 2026 rung; same question. | — |
| `starmer-out-in-2025` | Starmer out by...? | 2026-06-22 | $38.2M | 144k | UK date ladder (19 markets). Party insiders, not a military leak. | — |
| `will-china-invade-taiwan-by-june-30-2026` | Will China invade Taiwan by June 30, 2026? | 2026-07-01 | $12.0M | 45k | Second Taiwan deadline. | — |
| `putin-out-as-president-of-russia-by-june-30` | Putin out as President of Russia by June 30? | 2026-07-01 | $4.4M | 17k | Leader-exit deadline. Weak if it resolves No. | — |

## Ukraine battlefield

Map-capture ladders. `research/marketCandidates.md` found no fresh longshot whale on Pokrovsk; the suspected edge there is map-update latency, which this detector is not built for. Included as resolved date ladders and a weak control, not as insider labels.

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `will-russia-capture-pokrovsk-by` | Will Russia capture Pokrovsk by...? | 2025-08-08 | $4.0M | 15k | Town ladder. August 2025 rung resolved Yes. | — |
| `will-russia-capture-kupiansk-by` | Will Russia capture Kupiansk by...? | 2025-10-29 | $5.1M | 19k | Separate town, later date. | — |
| `will-russia-capture-kostyantynivka-by` | Will Russia capture Kostyantynivka by...? | 2026-08-19 | $10.0M | 38k | Separate town, 2026. | — |

## Awards and rankings

Embargoed lists and voted awards. Staff, labels, and academies know the result before the post.

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `who-will-hbo-doc-identify-as-satoshi` | Who will HBO doc identify as Satoshi? | 2024-10-09 | $44.3M | 167k | Filmmakers know the reveal. | — |
| `time-2024-person-of-the-year` | Time 2024 Person of the Year | 2024-12-12 | $1.7M | 6k | Magazine embargo. | — |
| `grammys-album-of-the-year-2025` | Grammys: Album of the Year | 2025-02-03 | $1.9M | 7k | Voted award. One category, not the whole show. | — |
| `oscars-best-picture` | Oscars: Best Picture | 2025-03-03 | $5.4M | 20k | Voted award, 2025 ceremony. | — |
| `nobel-peace-prize-winner-2025` | Nobel Peace Prize Winner 2025 | 2025-10-10 | $21.5M | 81k | Committee knows the name. Machado contract is the reported trade. | WSJ, account "6741" |
| `top-spotify-artist-2025-146` | Top Spotify Artist 2025 | 2025-12-03 | $90.0M | 339k | Spotify knows the ranking before the post. | — |
| `1-searched-person-on-google-this-year` | #1 Searched Person on Google this year? | 2025-12-08 | $57.1M | 215k | Google Year in Search. d4vd won. Sibling Google categories that day were not added. | Harvard / Unusual Whales |
| `game-awards-game-of-the-year-2025` | Game of the Year 2025 | 2025-12-12 | $40.5M | 153k | Jury knows the winner. | — |
| `time-2025-person-of-the-year` | Time 2025 Person of the Year | 2025-12-16 | $55.5M | 209k | Embargo. A small "will it be leaked" market the same week was not added. | — |
| `grammys-album-of-the-year-winner` | Grammys: Album of the Year Winner | 2026-02-02 | $1.5M | 6k | 2026 ceremony. Separate year from the 2025 album row. | — |
| `oscars-2026-best-picture-winner` | Oscars 2026: Best Picture Winner | 2026-03-16 | $12.9M | 48k | 2026 ceremony. | — |

## Policy announcements

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `will-biden-drop-out-of-presidential-race` | Biden drops out of presidential race? | 2024-07-21 | $21.1M | 80k | Campaign decision, resolved the day of the letter. Not a ballot outcome. | — |
| `tiktok-banned-in-the-us-before-may-2025` | TikTok banned in the US before May 2025? | 2025-01-22 | $119.7M | 451k | Enforcement call around a public statutory deadline. Largest event in this set. | — |
| `who-will-acquire-tiktok` | Who will acquire TikTok? | 2025-07-02 | $3.2M | 12k | Buyer. Deal talks leak. | — |
| `when-will-the-government-shutdown-end-545` | When will the Government shutdown end? | 2025-11-13 | $40.2M | 152k | Date ladder. Leadership knows the vote. | — |
| `tiktok-sale-announced-in-2025` | TikTok sale announced by...? | 2025-12-26 | $14.0M | 53k | Announcement-by-date. Related to the buyer market, later deadline. | — |

## Tech and product launches

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `will-tesla-launch-a-driverless-robtotaxi-service-before-july` | Will Tesla launch a driverless Robotaxi service before July? | 2025-07-05 | $11.9M | 45k | Company knows whether the service launched. | — |
| `when-will-gpt-5-be-released` | GPT-5 released by…? | 2025-08-07 | $7.3M | 27k | OpenAI ship date. Named in the same cluster as the browser wallets. | Harvard / Unusual Whales |
| `how-much-will-iphone-17-cost` | How much will iPhone 17 cost? | 2025-09-13 | $2.9M | 11k | Supply chain and the event script. Keynote word-bingo markets were under $1M and were not added. | — |
| `openai-browser-by-october-31` | OpenAI browser by October 31? | 2025-10-21 | $5.5M | 21k | Launch date. Reported cluster of fresh wallets in the 40 hours before launch. | Unusual Whales; OpenAI fired an employee |
| `gemini-3pt0-released-by` | Gemini 3.0 released by...? | 2025-11-18 | $16.4M | 62k | Google ship date. | — |
| `what-day-will-openai-release-a-new-frontier-model` | What day will OpenAI next release a new frontier model? | 2025-12-16 | $10.1M | 38k | Later than GPT-5. Day ladder. | — |
| `gpt-5pt5-released-by` | GPT-5.5 released by...? | 2026-04-23 | $1.5M | 6k | 2026 release ladder. | — |
| `gpt-5pt6-released-by` | GPT-5.6 released by...? | 2026-07-09 | $4.3M | 16k | 2026 release ladder. | — |

Sora's public-release markets were about $0.07M or less and were not added. Unusual Whales still names Sora next to GPT-5 and the browser.

## Entertainment

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `who-will-win-the-beast-games` | Who will win the Beast Games? | 2025-02-13 | $0.97M | 4k | Production knows the winner. Just under the $1M floor. Season 1. | — |
| `taylor-swift-and-travis-kelce-engaged-in-2025` | Taylor Swift and Travis Kelce engaged in 2025? | 2025-08-26 | $0.39M | 1k | Under the floor. Included because the trade is documented. | PokerScout, "romanticpaul" |
| `who-will-die-in-stranger-things-season-5` | Who will die in Stranger Things: Season 5? | 2026-01-05 | $83.7M | 316k | Writers and the edit know. No named wallet case found. | — |
| `who-will-win-the-beast-games-season-2-966` | Who will win the Beast Games: Season 2? | 2026-02-25 | $3.8M | 14k | Winner was heavily bought weeks before the finale. | PANews |

## Investigation announcement

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `which-crypto-company-will-zachxbt-expose-for-insider-trading` | Which crypto company will ZachXBT expose for insider trading? | 2026-02-26 | $39.7M | 150k | The report names Axiom. Tagged `crypto` on Gamma; it is an announcement, not a price market. | CoinDesk / Lookonchain, 12 wallets |

## Appointments

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `who-will-trump-nominate-for-treasury-secretary` | Who will Trump pick for Treasury Secretary? | 2024-11-23 | $6.1M | 23k | Transition leak before the announcement. | — |
| `who-will-be-trumps-defense-secretary` | Who will be Trump's Defense Secretary? | 2025-01-25 | $14.0M | 53k | Contested pick. | — |
| `who-will-be-trumps-attorney-general` | Who will be Trump's Attorney General? | 2025-02-05 | $11.1M | 42k | Contested pick. | — |
| `who-will-trump-announce-as-next-fed-chair-before-july` | Who will Trump announce as next Fed Chair before July? | 2025-07-02 | $4.8M | 18k | Early deadline. The later confirmation is a separate row. | — |
| `who-will-be-confirmed-as-fed-chair` | Who will be confirmed as Fed Chair? | 2026-05-14 | $64.5M | 243k | White House nomination. An appointment, not an FOMC rates decision. | — |

## Courts

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `trump-sentenced-to-how-much-prison-time` | Trump prison time in NY case before election? | 2024-11-05 | $10.1M | 38k | Sentence range. The court can know before the hearing. | — |
| `how-many-constitutional-court-justices-will-vote-for-yoons-impeachment` | How many Constitutional Court justices will vote for Yoon's impeachment? | 2025-04-04 | $7.7M | 29k | Vote count can leak. Same saga as the Yoon removal row, different fact. | — |
| `yoon-insurrection-case-prison-sentence` | Yoon Suk Yeol Insurrection Case Prison Time? | 2026-02-19 | $4.4M | 17k | Later criminal sentence, not the 2025 removal. | — |

## Fed control

Scheduled rate decisions. The statement is drafted in-house, but this is the low-leak macro control, not a military or embargo leak. Only three meetings, spread out. The $100M–$660M meetings listed in the method were left out.

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `fed-interest-rates-july-2024` | Fed Interest Rates: July 2024 | 2024-07-31 | $2.8M | 11k | FOMC. Small book. | — |
| `fed-interest-rates-december-2024` | Fed decision in December? | 2024-12-18 | $58.8M | 222k | FOMC. | — |
| `fed-decision-in-march` | Fed decision in March? | 2025-03-19 | $78.0M | 294k | FOMC. | — |

## Election control

Ballot outcomes. Included only as controls. The US presidential winner market was left out because of its size.

| slug | title | endDate | volume | est fills | why | case |
|---|---|---|---:|---:|---|---|
| `texas-presidential-election-winner` | Texas Presidential Election Winner | 2024-11-06 | $13.4M | 51k | 2024 state result. Stand-in for the $3.69B national market. | — |
| `which-party-wins-most-seats-in-canadian-election` | Which Party wins most seats in Canadian election? | 2025-04-30 | $12.7M | 48k | 2025 parliamentary result. | — |
| `prime-minister-of-japan-after-snap-election` | Prime Minister of Japan after snap election? | 2026-02-18 | $8.5M | 32k | 2026 snap election. | — |

## Reported insider cases

Already in `configs/insiderCases.yaml`, not repeated here:

- US/Israel strike on Iran, 28 Feb 2026, and the ceasefire ladder. Harvard Law School Forum on Corporate Governance, "From Iran to Taylor Swift" (25 Mar 2026): https://corpgov.law.harvard.edu/2026/03/25/from-iran-to-taylor-swift-informed-trading-in-prediction-markets/
- Maduro capture, early January 2026. Same Harvard piece (Burdensome-Mix).
- Israeli reservist and a civilian charged over classified strike bets, June 2025–January 2026. The Guardian (6 May 2026): https://www.theguardian.com/world/2026/may/06/polymarket-israel-iran-war-arrest — the June 2025 book is `israel-strike-on-iran-on`, already in the config.

Mapped into this universe:

- Nobel Peace Prize, 10 Oct 2025. New account "6741", more than $50k, María Corina Machado. WSJ: https://www.wsj.com/finance/stocks/polymarket-nobel-peace-prize-bets-c34ee0c8 — `nobel-peace-prize-winner-2025`.
- Google Year in Search 2025. A trader made over $1M; the winner was d4vd. Harvard piece above, and the Unusual Whales writeup quoted in coverage of the OpenAI firing. `1-searched-person-on-google-this-year`.
- OpenAI browser launch, October 2025, plus GPT-5 and Sora in the same reported cluster. Unusual Whales: 13 fresh wallets bet $309,486 in the 40 hours before the browser launch. OpenAI fired an employee for using confidential information on prediction markets (WIRED, restated in the Harvard piece). `openai-browser-by-october-31`, `when-will-gpt-5-be-released`. Sora markets were too small to fetch.
- Taylor Swift and Travis Kelce engaged, 26 Aug 2025. Account "romanticpaul". PokerScout: https://www.pokerscout.com/insider-trading-on-polymarket-foretold-taylor-swifts-engagement/ — `taylor-swift-and-travis-kelce-engaged-in-2025` ($0.39M).
- ZachXBT names Axiom, 26 Feb 2026. Lookonchain: 12 wallets, about $1.0M profit. CoinDesk: https://www.coindesk.com/markets/2026/02/27/polymarket-bettors-appear-to-have-insider-traded-on-a-market-designed-to-catch-insider-traders — `which-crypto-company-will-zachxbt-expose-for-insider-trading` ($39.7M).
- Beast Games season 2. On Polymarket the winner's price was pushed above 90% weeks before the finale. PANews: https://www.panews.io/articles/019c9d67-fe62-7162-9514-032b0a261049 — `who-will-win-the-beast-games-season-2-966`. The Kalshi fine of a MrBeast editor is a different venue.

Looked up and not given a slug here: Apple WWDC and keynote-mention markets (under $1M; the iPhone 17 price market is included instead), North Korea missile and leadership markets (under $1M or still open), the Hezbollah pager-responsibility market (~$0.09M), Sinwar's death (~$0.40M), Sam Altman's November 2023 return (before the window).
