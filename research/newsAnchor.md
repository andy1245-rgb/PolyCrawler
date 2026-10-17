# News-anchor test on the shipped military rule (pre-news vs news-chasers)

Script: `scripts/research/newsAnchor.py` (run 2026-10-09 06:59Z).
Companion to `research/ideasResearch.md` #3 and `research/militaryCategory.md`.

## Method

1. Reproduces the shipped cell via the `militarySweep.py` code path (fresh <=5d,
   <=3 markets, burst >= $5k, tape price <= 0.35, military slug keywords;
   realistic fill = next taker price within 5 min). Rebuilt n=428 signals across 28 events (shipped docs report 425-428; runs vary by +-1-3 on    a float-tie at the exact $5k burst boundary — parallel float summation order).
2. Per event, GDELT DOC 2.0 artlist (free, no key), space-joined keywords = AND
   (verified by probe: real+nonsense word pair returns 0 articles), sorted
   ascending within a window [firstSignal-30d, resolution+1d, capped 89d].
   The FIRST matching article's `seendate` (15-min resolution) is the
   per-event firstNewsTs anchor. Responses cached to `data/raw/gdelt/`
   (read-only GETs, one request per event, 15s spacing + one bounded
   retry pass for transient 429/timeout failures).
3. Split: pre-news = signal ts < firstNewsTs + 2h grace; post-news otherwise.
   Event-level bootstrap (2000 resamples, seed 7) on retReal, same method as
   `militaryCategory.py`.

**Bias note:** anchors are built to fail conservative. A `truncated` quality flag
means the topic was already covered when the search window opens, so the anchor
is a LOWER bound on true first-news time and some genuinely pre-news signals are
misfiled as post-news. This biases AGAINST the pre-news hypothesis — the safe
direction for a promotion decision.

## Anchor coverage: 28/28 events, 428/428 signals

(19 events truncated: pre-existing topic coverage at window start; 0 without an anchor)

| event | n | pre(2h) | anchor quality | firstNews (UTC) | first article | query |
|---|---:|---:|---|---|---|---|
| will-israel-invade-lebanon-in-september | 3 | 0 | truncated | 2024-09-01 17:00 | Commentary : Netanyahu betrayal of hostages could drag U . S | `Israel invasion Lebanon` |
| israel-strike-on-iranian-nuclear-facility-in-2024 | 3 | 0 | truncated | 2024-10-01 08:30 | Israel devastation of Hezbollah puts Iran in a corner | `Israel "Iranian nuclear"` |
| russia-x-ukraine-ceasefire-in-2024 | 2 | 0 | truncated | 2024-10-08 10:45 | Кремль пропонує план закінчення війни в Україні : Лавров ого | `Russia Ukraine ceasefire` |
| israel-x-hezbollah-ceasefire-in-2024 | 1 | 0 | truncated | 2024-10-10 16:30 | Hezbollah :  Israele cessate il fuoco o colpiremo Haifa   | `"Hezbollah ceasefire"` |
| will-israel-invade-syria-in-2024 | 2 | 0 | truncated | 2024-11-10 02:45 | ترمب في البيت الأبيض ..!! – كتابات | `Israel invasion Syria` |
| russia-x-ukraine-ceasefire-in-2025 | 34 | 7 | truncated | 2025-10-05 09:00 | Зеленський відреагував на атаку РФ 5 жовтня і заявив , що За | `Russia Ukraine ceasefire` |
| zelenskyy-out-as-ukraine-president-before-july | 3 | 3 | truncated | 2025-04-04 09:00 | Чи розпочнеться конструктивний діалог інтернет - провайдерів | `Zelensky Ukraine president` |
| russia-x-ukraine-ceasefire-before-july | 3 | 1 | truncated | 2025-04-04 08:30 | Russia accused by Britain and France of delaying ceasefire t | `Russia Ukraine ceasefire` |
| will-russia-capture-kupiansk-by | 2 | 2 | truncated | 2025-08-03 03:45 | Russo - Ukraine War - 02 August 2025 | `Kupiansk` |
| will-russia-capture-kostyantynivka-by | 1 | 1 | truncated | 2025-06-05 10:45 | В ОВА рассказали , сколько гражданских проживает на Донетчин | `Kostyantynivka` |
| israel-x-hamas-ceasefire-before-august | 3 | 0 | ok | 2025-07-02 03:45 | Trump anuncia alto el fuego de 60 días en Gaza | `"Hamas ceasefire"` |
| will-russia-capture-pokrovsk-by | 1 | 0 | ok | 2025-07-02 06:45 | Russia ramps up offensives on two fronts in Ukraine as both  | `Pokrovsk` |
| russia-x-ukraine-ceasefire-before-october | 5 | 0 | truncated | 2025-07-11 18:00 | Буданов : 40 відсотків боєприпасів армії РФ - з КНДР – DW –  | `Russia Ukraine ceasefire` |
| maduro-out-in-2025 | 25 | 2 | truncated | 2025-10-07 13:00 | Ağ Ev Venesuela ilə diplomatik razılaşma səylərini dayandırı | `Maduro Venezuela` |
| will-the-us-invade-venezuela-in-2025 | 2 | 0 | truncated | 2025-12-04 16:00 | Actor venezolano hizo férrea defensa a Maduro y vivió tenso  | `Venezuela invade` |
| us-strikes-iran-by | 140 | 0 | ok | 2025-12-12 01:45 | Trump : Mideast peace achieved after strikes on Iran nuclear | `"US strikes Iran"` |
| khamenei-out-as-supreme-leader-of-iran-by-march-31 | 17 | 0 | ok | 2025-12-07 01:15 | How Iran Regime Intentionally Devalues Its Currency To Fund  | `Khamenei` |
| israel-strikes-iran-by-january-31-2026 | 15 | 0 | ok | 2025-12-15 22:30 | 2025 In Review Fast Facts | `"Israel strikes Iran"` |
| israel-strikes-iran-by-january-16-2026-418 | 1 | 0 | ok | 2025-12-15 22:30 | 2025 In Review Fast Facts | `"Israel strikes Iran"` |
| usisrael-strikes-iran-by | 4 | 0 | ok | 2025-12-21 17:30 | В Париже приветствуют готовность Путина к диалогу с Макроном | `"US strikes Iran"` |
| khamenei-out-as-supreme-leader-of-iran-by-february-28 | 17 | 0 | truncated | 2025-12-21 11:00 |   The American Ayatollahs : President Obama Crushes The Neoc | `Khamenei` |
| will-the-iranian-regime-fall-by-march-31 | 24 | 0 | truncated | 2026-01-29 07:45 | Implementation Of Iran - Related United Nations Security Cou | `"Iranian regime"` |
| us-x-iran-ceasefire-by | 53 | 0 | ok | 2026-02-25 05:00 | Trump SOTU Address Overstates Ending Eight Wars | `"Iran ceasefire" "United States"` |
| will-china-invade-taiwan-by-june-30-2026 | 1 | 0 | truncated | 2026-04-04 07:15 | 2026 metų didžiausių pasaulio armijų reitingas : viena šalis | `China Taiwan invasion` |
| russia-x-ukraine-ceasefire-by-april-30-2026 | 1 | 0 | truncated | 2026-03-11 10:15 | Вибори президента : умови для голосування військових на спец | `Russia Ukraine ceasefire` |
| us-x-iran-permanent-peace-deal-by | 60 | 0 | truncated | 2026-03-22 05:15 | Ιράν - Ισραήλ : Πυρηνική κλιμάκωση μετά τις επιθέσεις σε Ντι | `"peace deal" "United States" Iran` |
| israel-x-hezbollah-ceasefire-by | 2 | 0 | ok | 2026-03-18 12:45 | Israelis had just returned to this northern town after the l | `"Hezbollah ceasefire"` |
| us-x-iran-ceasefire-extended-by | 3 | 0 | truncated | 2026-03-27 14:00 | Bitcoin falls under $69K due to $14B options expiry | `"Iran ceasefire" extended` |

## Pre-news vs post-news (grace sensitivity)

| subset | n | events | win% | ret | retReal | boot p5 | boot p95 | P(>0) | H1 | H2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pre-news  grace 0h | 16 | 6 | 25% | -0.225 | -0.217 | -1.000 | +0.450 | 24% | +0.392 | -1.000 |
| post-news grace 0h | 412 | 25 | 35% | +1.086 | +1.220 | +0.292 | +1.762 | 98% | +0.003 | +1.260 |
| pre-news  grace 2h (shipped) | 16 | 6 | 25% | -0.225 | -0.217 | -1.000 | +0.450 | 26% | +0.392 | -1.000 |
| post-news grace 2h (shipped) | 412 | 25 | 35% | +1.086 | +1.220 | +0.337 | +1.731 | 98% | +0.003 | +1.260 |
| pre-news  grace 12h | 16 | 6 | 25% | -0.225 | -0.217 | -1.000 | +0.340 | 24% | +0.392 | -1.000 |
| post-news grace 12h | 412 | 25 | 35% | +1.086 | +1.220 | +0.301 | +1.701 | 98% | +0.003 | +1.260 |
| unanchored events | 0 | 0 | - | - | - | - | - | - | - | - |
| all shipped-cell signals | 428 | 28 | 34% | +1.037 | +1.166 | +0.284 | +1.690 | 98% | +0.162 | +1.221 |

ret = insider's own price (upper bound); retReal = next-taker-price within 5 min
(realistic fill, the shipped-cell convention). H1/H2 = mean retReal before/after
2025-06-01.

## Decision rule: DO NOT PROMOTE — and the result reverses the hypothesis

Full-coverage run (28/28 events anchored, 2026-10-09 06:50Z): pre-news n=16
across 6 events, win 25%, retReal −22%, P(>0) 26% — **the pre-news subset is
a small loser, not the edge**. The entire +117% shipped-cell return sits in
the post-news subset (n=412, retReal +122%, P(>0) 98%, positive H2, ~zero H1).
Grace windows 0h/2h/12h do not change the split.

Reading: the copied fresh-big-bets are NOT front-running first public news —
they pile in *after* coverage exists (or the anchor misses true first news
because coverage predates the window; the truncated flags say exactly that).
Either way a "no breaking news in N hours" gate would have deleted the edge,
not isolated it. Do not add it. Interpretive caveat: edge concentrated
post-news looks more like fast news-ride/momentum than misappropriation —
consistent with the enforcement record describing *different* traders than
the ones this rule copies.

Signals CSV: `data/research/newsAnchorSignals.csv` (one row per shipped-cell signal,
with isPreNews / firstNewsTs / anchor quality).
