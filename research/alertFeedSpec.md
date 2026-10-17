# Implementable product spec — paid insider-burst alert feed (Money Path A)

Status: BUILD-READY spec written 2026-10-17. Nothing here is open-ended: every
choice is either decided below or listed in §8 (the only section reserved for
the operator). A second task executes this spec over 2–3 weeks. No code was
changed to produce this document.

Sources: `research/monetization.md` (R9 scan), `research/relayV2Sunset.md`,
direct reads of `scripts/liveWatcher.py`, `scripts/dailyCatchup.sh`,
`scripts/paperMarkToMarket.py`, `scripts/research/accountDossiers.py`,
`src/polycrawler/discovery/engine.py`, and measured sizes of `data/live/*` +
`data/raw/*` (2026-10-17). Alert sample: `data/live/signals.csv`, 9 alerts
over the tape's first ~3 days; watcher live at the time of writing (log shows
1,335 open military markets / 234 events being watched).

---

## 1. Product: positioning, names, pitch, legal copy

### 1.1 Positioning (decided)

Sell **detection and forensics**, not trading advice and not copy-execution:

- What a subscriber gets: real-time alert the moment a qualifying burst prints
  on Polymarket's military/geopolitics tape, plus an on-chain **evidence
  dossier** for the bursting wallet — funding trails (where the money came
  from, which chain, which bridge/relay route), parent fingerprints, and
  same-second co-trade linkage to other accounts.
- What we never do: position sizing, entries/exits, "buy this", automated or
  manual execution of any order, "copy our book". The paper copy-book exists
  and is published **as an honesty metric about the signals**, not as an offer.
- Why this framing shelters us (from the R9 scan: enforcement precedent
  Spagnuolo / Maduro-soldier / OpenAI firing all target **participants**; no
  seller prosecution found 2024–2026; but Polymarket actively counter-pressures
  copy-piggyback startups and monitors Telegram): an evidence-and-detection
  vendor is a research product with buyers beyond copy-traders (researchers,
  journalists, compliance, the platform itself), and nothing we ship executes
  or recommends a trade.

The core differentiator is real and unclaimed: every competitor in the scan
(UW $17/mo, PolyPulse $29–199, PolyAlertHub, Hashdive) sells a **label**
("potential insider", size threshold, age heuristic). **Nobody sells the
funding-trail/parent-fingerprint dossier** — attribution of *who is behind*
the burst. That is the product.

### 1.2 Name candidates (3+; pick in §8-1)

| Candidate | Rationale | Risk |
|---|---|---|
| **BurstDossier** | Names both halves of the product: the alert (burst) and the differentiator (dossier). Forensic, neutral. | None serious; slightly long handle (`@burstdossier`). |
| **TrailWatch** | Emphasizes the funding trail; clean for a general forensics brand. | Generic; collides with blockchain-analytics naming space. |
| **PolyForensics** | Immediately legible vertical + discipline. | "Poly" prefix is crowded (PolyPulse, PolyAlertHub…); reads as a Polymarket-only shop (fine for MVP). |
| **FreshTrail** | Encodes the rule (fresh wallets) + differentiator (trail). | "Fresh" undersells forensics depth. |

Recommendation: **BurstDossier**. Decided unless overridden in §8-1.

### 1.3 One-line pitch

> **BurstDossier — on-chain forensics for Polymarket. Real-time alerts when a
> fresh wallet drops a five-figure burst on a military/geopolitics market,
> with the funding trail that shows where the money came from.**

### 1.4 Legal-safe copy block (canonical; paste in channel descriptions, the
evidence page, every digest. Short footer version for alert posts.)

Full version (landing/channel description):

> **BurstDossier is an on-chain research and alerting service.** We publish
> real-time detection events ("bursts") observed on Polymarket's public trade
> tape, together with verifiable on-chain evidence — funding transfers, bridge
> and relay origins, and same-second co-trading links between wallets — plus
> wallet-level forensics on request.
>
> **Nothing we publish is financial advice, a recommendation, or an offer to
> buy or sell anything.** BurstDossier does not trade on your behalf, does not
> manage funds, and is not a copy-trading or signal-copying service: we do not
> execute, route, or automate orders of any kind. We make no representation
> that any information in this service is accurate, complete, or timely, and
> we expressly do not warrant that acting on any alert or dossier will be
> profitable. Markets are adversarial; our detections can be wrong, late, or
> gamed, including deliberately (spoofing, wash bursts, market-maker sweeps).
>
> All data is derived from public, third-party sources (Polymarket public APIs
> and public blockchains) and is provided "as is". Wallet addresses and their
> transaction histories are public on-chain records; we publish that evidence
> only, and never assert the real-world identity of any wallet. You are solely
> responsible for any decision you make based on this service. BurstDossier is
> not affiliated with, endorsed by, or sponsored by Polymarket or any trading
> venue. Polymarket participants are solely responsible for their own conduct;
> this service facilitates detection and research, not trading.

Alert footer (every post): `Evidence, not advice. Dossier: <link>. Terms: <link>.`
(The "Terms" link points to the copy block on the static evidence page.)

### 1.5 Honesty policy baked into the product

- The paper copy-book (`data/live/trajectory.csv`, 4-week trend) is published
  on the evidence page with its honest numbers, including negative months.
  This is a differentiator (nobody in the scan publishes verified hit-rates)
  and a shield: it proves the product is sold as detection, with the trading
  question answered transparently whatever the answer is.
- Dossiers state trace coverage honestly: if the origin is unresolved
  (non-EVM origin, non-relay route, or trace budget exhausted), the dossier
  says so in a dedicated field. Never fabricate attribution.

---

## 2. Channel decision matrix + distribution

### 2.1 Matrix (decided: Telegram primary, static web evidence page, manual email digest)

| Criterion | Discord bot | **Telegram channel** | Web feed + email digest |
|---|---|---|---|
| Ops cost | Bot process + role-gating webhook code + bot token | **~0 code**: two channels (free/paid), a single bot token for automated posting; manual invite-link gating | Static page trivial; email = real infra (sender domain, SPF/DKIM, bounce handling) |
| Latency | Instant | **Instant** (bot posts on CSV tail) | Web: instant but needs auth+websocket build; email: minutes–hours (not real-time) |
| Pay friction | Needs bot↔Stripe webhook to assign roles | **Manual but near-zero**: Stripe Payment Link → confirm payment → paste one-use invite link to paid channel (seconds per sub) | Needs checkout + account system (weeks) |
| Retention | High (app pinned) | **High** (this lane's audience is Telegram-native — competitor whale-alert scene runs there; Polymarket itself watches Telegram) | Medium (read-once emails) |
| Risk | Second-choice platform; role-gating code = build debt | Manual gating doesn't scale past ~50 subs (fine — first-revenue target is 20) | Largest build, defers launch |

**Decision: Telegram.** Two channels (`BurstDossier — Free (delayed)`,
`BurstDossier — Paid (real-time)`), one bot token (post-only, no user-input
commands in MVP). The web property is a **static evidence page** (§3-6), not a
feed. Email exists only as a manual weekly digest BCC to paid subs. Discord is
the tier-2 expansion, not MVP.

### 2.2 Distribution — concrete step list (executed Week 2)

1. **X account + example-casework posts (the ad unit).** From the R9 scan:
   PolyAlertHub's entire X presence is real-time alert screenshots; the launch
   trigger in monetization.md is "one fully-attributed high-profile military
   burst dossier published on X in real time". Plan: 3 canned post formats —
   (a) alert embed screenshot (redacted: wallet address shown, it is public
   data), (b) public dossier card (funding trail chart, e.g. Dune/graph render
   or annotated table), (c) paper-metrics strip from `trajectory.csv`. Also
   quote-post our own alert within minutes of it firing when it's newsworthy.
2. **predictionmarket.tools directory listing.** The R9 scan verified the
   directory (60+ tools, ≥8 alert products, checked 2026-09-29). Submit
   BurstDossier under alerts/forensics with the pitch + evidence-page URL.
   This is the highest-intent free distribution surface found.
3. **Cold DMs to known Polymarket traders.** Sources of targets: public
   leaderboards (data-api), followers of PolyPulse/PolyAlertHub X accounts,
   active wallets from the watcher's own state (public handles only — never
   DM a real-life identity). Cadence: 50/week, message = one example dossier +
   one free month code. Suppress: link spam into communities that ban promos.
4. **Free tier as the funnel**: the delayed free channel is the shareable
   artifact (counts + weekly public dossier); paid real-time is the upgrade
   (PolyPulse's exact $0-delayed → $29-realtime ladder, proven in-market).

---

## 3. MVP feature list mapped EXACTLY to existing infra

Verified against the live watcher and repo as of 2026-10-17.

| # | Feature | Status | Mechanism |
|---|---|---|---|
| 1 | Real-time burst alert | **exists today** | `scripts/liveWatcher.py` → `data/live/signals.csv` (append, one row per alert): RTDS push tape (sub-second) + `/v2/trades` CASH≥$5k gap-rescue every 120 s. Rule: ≥$5k burst in a 600 s window, avg px ≤ 0.35, account age ≤ 5 d, ≤ 3 markets seen, fee-enabled markets excluded — i.e. alerts land in the fee-free geopolitics lane. Alert sample: 9 alerts / first ~3 days → **0–10/day, low-frequency high-conviction positioning**. |
| 2 | Runnable ledger under each alert | **exists today** | `signals.csv` carries full context: `alertTs, account, eventSlug, question, marketId, outcome, burstUsd, avgPrice, ageDays, marketsSeen`; the daily paper copy book (`paperPnl.py` → `paperMarkToMarket.py` → `trajectory.csv`, cron via `dailyCatchup.sh`) publishes the honesty strip. Feed states clearly: ledger = *how our signals look when copied at face value*, evidence = the product. |
| 3 | CLOB book-size context | **exists today** | `bookSize()` writes `bestAsk`, `askSize`, `takeableShares` (ask depth within +10% slip of burst avg) into every `signals.csv` row. Live sample: Iran-invasion alert had 311 shares at 0.17 best ask, 213k takeable. |
| 4 | Wallet age + first-trade verification | **exists today** | `verifyAccountAge()` one-time `/activity` rescue: accounts first seen in backfill are gated until an empty 5-day pre-bet activity window proves genuine freshness; failure closes the gate (never fires unverified). |
| 5 | Funding-trail / parent dossier | **BUILD (Week 2)** | On-demand trace of the alerted account by a new feed-side builder that reuses `src/polycrawler/discovery` (Etherscan-v2 funding edges on Polygon, relay origin resolution, co-trade window linking in `links.py`) and the dossier shape of `scripts/research/accountDossiers.py`. Trigger: automatically on every paid-channel alert; budget-capped (§6.2). **CACHE-FIRST design (decided, §6.2)**: check local caches first (`data/raw/{relay,etherscan,activity}` = 8.6 GB accumulated; 356 relay files frozen), then live with rate caps; persist per-account results to `data/rawFeed/dossiers/<account>.json`. **Relay-v2 sunset (retired 2026-11-24)** handled per `relayV2Sunset.md`: v2 remains usable until sunset; the free Relay v3 `x-api-key` is created in **Week 1** and the golden-curl check (`?fillTxHash=0x131e0ad5…` → expects user `0xcd86a2bb…`, origin chain 1, inTx `0xbc17d7d8…`) is run before we rely on v3; if keyless visibility fails, fall back to the on-chain origin-trail (EVM-exact, Solana/Tron origins → honest `unresolvedOrigins`). |
| 6 | Daily mark tracker / outcomes digest | **exists today** | `openPositions.csv` (full open book, marked daily) + `trajectory.csv` (per-date trend, 4-week gradeable) + `paperPnl.csv` (resolution outcomes). Free tier gets the aggregate strip delayed; paid gets the raw daily tables. |
| 7 | Dashboard | **decided: skip interactive; build static evidence page** (`dashboard/` folder does not exist anywhere in the repo — there is nothing to extend) | One script renders `trajectory.csv` + `paperPnl.csv` + a redacted example dossier into a single static `evidence.html`, served from the existing box (or GitHub Pages). No auth, no websocket, no backend. |

**Total MVP build surface:** feed tail/posting process (Week 1), dossier
builder + renderer (Week 2), static evidence page (Week 1 v0, Week 2 polish).
Everything else is consumption of files that already exist and update
themselves.

---

## 4. Pricing ladder + checkout

### 4.1 Anchors (from R9 live checks, 2026-10-17)

- **Unusual Whales / Unusual Predictions: $17/mo** for full "potential insider
  alerts" — the label is commodity-priced. We do not compete on price against
  the label; we price above it on the dossier.
- **PolyPulse: $0 (15-min delay) / $29 / $79 / $199** — the $0-delayed→$29-
  realtime ladder is proven in this exact lane; $79–199 buys execution/API.
- **OddsPipe: $49 / $99 / $299** for normalized PM data — the data-API ceiling.
- Hashdive's exit into Unusual Whales = consolidation; a differentiated vendor
  is a takeout target rather than a casualty of it.

### 4.2 Ladder (decided; exact numbers confirmable in §8-2)

| Tier | Price (default) | What they get | Delay |
|---|---|---|---|
| **Free** | $0 | Delayed aggregate daily counts (N alerts, events covered — no addresses, no dossiers, no book context); weekly digest with one public dossier; evidence page | **24 h** |
| **Analyst** | **$29/mo** | Real-time alerts (full row: burstUsd, avgPrice, age, marketsSeen, bestAsk/askSize/takeable); daily marks tables; **2 dossiers/month on any alerted account**; full alert-history archive | real-time |
| **Desk** | **$59/mo** | Everything + dossier on demand up to 20/month (fair-use), cluster-link tables (same-second co-trade windows), CSV export on request, priority response | real-time |

No API tier in MVP (OddsPipe's lane is Phase 2 / Path B; sell the dataset later
from the same exhaust). Annual = 10 months' price for 12, offered via a second
Stripe link; not promoted until ≥10 paying subs exist.

### 4.3 Checkout (decided: Stripe Payment Links; Paddle/Gumroad rejected)

- **Stripe Payment Links**: subscriptions, no website needed, per-seat roster
  managed manually in the Stripe dashboard. Fees 2.9% + $0.30 → on $29 that is
  $1.14 (96% margin). Set up inside the existing (or newly created) Stripe
  account; enable Stripe Tax at toggle time.
- Gumroad rejected: ~10% flat — $2.90/mo per $29 sub, 2.5× Stripe's take for
  zero benefit here. Paddle rejected for MVP: ~5% + $0.50 and MoR approval
  cycle (business verification, product review) before first charge; revisit
  if cross-border VAT handling ever becomes a recurring chore (that is the
  one thing MoR buys).
- Delivery flow per paid signup (manual, ~60 s): payment notification email →
  confirm → generate one-use Telegram invite link to paid channel → DM it.
- Unpaid-expiry policy: end of billing cycle, removal from paid channel, one
  grace DM.

### 4.4 Per-channel ops runtimes (decided)

| Channel | Runtime |
|---|---|
| Telegram paid | real-time post, seconds after CSV append |
| Telegram free | same alert posted 24 h later by the same job skipping paid-channel posts during the delay window |
| Email digest | manual weekly compose (MVP), BCC to paid roster |
| Evidence page | regenerated on demand / weekly |

---

## 5. Build plan — 3 weekly milestones (owner tasks only)

Owner = the operator + the implementing task. Nothing here requires people or
infra that don't exist. All runs on the existing box.

**Week 1 — plumbing + storefront**
1. `feedTail` process: tail `data/live/signals.csv` (append-only → safe
   concurrent read; do NOT consume `state.json` — it is a 14.7 MB full rewrite,
   not atomic), dedupe/format/post to both Telegram channels with the 24 h
   free-tier delay; own watchdog log under `logs/`. (Not a second RTDS adapter
   yet — see §6.3.)
2. Telegram channels + bot token; channel descriptions = §1.4 copy block.
3. Stripe Payment Links (3 SKUs) + roster sheet; one-use invite flow doc'd.
4. Static evidence page v0: trajectory strip + latest marks + copy block + terms.
5. Relay v3 self-serve key created; golden-curl visibility check run (§3-5).
6. Directory submission drafted; X account created (posts start Week 2).

**Week 2 — the differentiator + launch**
1. Dossier builder service (cache-first, budget-capped, persisted JSON) +
   dossier renderer (markdown/PNG card), auto-trace on every paid alert.
2. Public launch: one real-time X casework post (alert + dossier card +
   accuracy caveat) the first time an attributable military burst prints.
3. Directory listing live; DM outreach at 50/week; free channel seeded.
4. Manual email digest #1; manual precision audit of all alerts to date
   (verdict-sample method from `leadGate.md`/`verdictBenchmark.py`).

**Week 3 — hardening + review loop**
1. Watchdog: alert-staleness alarm (no CSV heartbeat > 30 min → pager via
   free channel note), Telegram-post retry/fallback path (manual X post).
2. Relay v3 dependency live behind the cache-first path if visibility
   confirmed; on-chain-trail fallback documented otherwise (no code required
   pre-sunset).
3. First weekly review (§7 cadence) with the metrics snapshot; decide Discord
   bot build only if paid subs ≥ 15 (tier-2 trigger, not MVP).

**Stays manual in MVP (decided):** payment follow-up + invite gating (~60 s
per sub), dossier public-post curation (which dossiers become X casework),
weekly digest writing, precision audits. All are sub-1 h/week at ≤ 30 subs.

**Costs (measured/sunk):**

| Item | Cost |
|---|---|
| Hosting | ~$0 — the box already runs the watcher + 3 cron jobs; the tail process adds negligible RAM/CPU (§6.2) |
| Domain | ~$12/yr |
| Telegram + bot token + static page | $0 |
| Relay v3 key | $0 (self-serve) |
| Stripe | 2.9% + $0.30 per charge (usage) |
| **Total fixed sunk** | **≈ $1–2/mo + domain** |

---

## 6. Ops + risk

### 6.1 API key inventory (verified from `.env` / code, 2026-10-17)

| Key | Status | Notes |
|---|---|---|
| `ETHERSCAN_API_KEY` | exists (free) | Discovery funding traces via `api.etherscan.io/v2`; free tier covers chains {1, 137, 42161} only; bounded by `etherscanMaxPages=10` and cache (`data/raw/etherscan/`) |
| `ALCHEMY_API_KEY` | exists (free, Polygon-scoped) | Solver-payout confirmation in `engine.confirmSolverPayout`; multi-chain origins would need extra free apps (only if on-chain fallback activates) |
| Gamma / Data-API / CLOB / RTDS | **no key needed** | Watcher runs keyless today |
| `RELAY_API_KEY` (Relay v3 `x-api-key`) | **add in Week 1** | Free, self-serve, dashboard.relay.link; 200 req/min default (~3.3 rps vs current 1 rps); required post 2026-11-24 sunset |
| Telegram bot token | **add Week 1** | Free; post-only |
| Stripe keys | **add Week 1** | Usage-priced |
| `DUNE_API_KEY` | optional, not needed for MVP | `duneOrderBurst.py` fallback only |

### 6.2 Capacity + cohabitation (measured; the feed never touches the watcher)

- Watcher writes: `state.json` 14.7 MB full-rewrite/~30 s, `events.json`
  546 KB/~5 min, `signals.csv` 2.7 KB (append-only), `trajectory.csv`
  (append). State: 15,260 tracked accounts, 1,335 markets watermarked,
  234 events. The tail process reading only `signals.csv` is trivially cheap.
- Existing cron cohabitants: `dailyCatchup.sh` (10 min, self-heals the
  watcher via `pgrep -f liveWatcher.py`), `orderBurstMonitor` (20 min),
  `orderBurstOnchain` (30 min, flock-guarded). Any new feed cron entry must
  follow the same flock pattern and must **not** collide with the
  `liveWatcher.py` pgrep pattern.
- **Dossier budget caps (decided):** per informed account ≤ 20 min wall-clock
  and ≤ 50 live host calls; cache hits (`data/raw/` = 8.6 GB) are free; all
  live calls go through the existing rate-limited `HttpSession` conventions
  (Etherscan free ~5 rps class limits; Relay 1 rps now → 3.3 rps on v3);
  partial results are published as partial, never padded.
- One concurrent RTDS feed connection: `rtdsTape` is a per-process daemon
  thread; a second independent connection is a supported design (§6.3), with
  no documented per-IP connection limit (risk-registered).

### 6.3 Second-adapter design (fully spelled; built only on trigger)

Trigger: the feed needs thresholds that differ from the paper-graded rule
(e.g. a $3k Tier-Analyst alert lane) **or** the paper rule changes. Until
then the MVP consumes the watcher's CSV because that identity IS the
auditable product: **feed alerts = the graded paper cells.**

Design when triggered — `scripts/feedAdapter.py`, a separate process:

1. Own process name (never matching `liveWatcher.py` in `pgrep`; cron entry
   flock-guarded like `orderBurstOnchain`).
2. Own RTDS connection via `scripts/rtdsTape.py` (import, own queue, own
   reconnect state) + own `/v2/trades` CASH≥$5k gap-rescue poll — identical
   mechanics to the watcher, recomposed per the feed's config (`FEED_RULES`:
   min burst USD, max price, max age, max markets).
3. Own state file `data/liveFeed/state.json` (fresh account ages computed
   from this adapter's own tape — no paper-gate tainting) + own append-only
   `data/liveFeed/signals.csv`.
4. Writes only under `data/liveFeed/`; reads the shared market universe
   read-only (`events.json` cache). Consumer (`feedTail`) is pointed at
   `liveFeed/signals.csv` by one config change.

### 6.4 Privacy (decided policy)

Wallet addresses and their transactions are public on-chain records; the
product publishes on-chain evidence only. Hard rules: never publish,
speculate, or accept from users any real-world identity link (names, handles,
employers) for a wallet — not even for enforcement-adjacent casework; link to
public court/press documents only if a wallet is publicly identified there;
no email-address harvesting beyond Stripe's own roster; free channel shows
addresses (public data) but never builds identity profiles. Doxxing rules:
identifying a person behind a wallet is out of scope of the product and out of
bounds of the operator, full stop.

### 6.5 Kill / halt policy (decided triggers)

| Trigger | Action |
|---|---|
| API bans / sustained 429 storms > 24 h (Etherscan, Relay, data-api) | Degrade to free-tier-delayed mode for everyone + public notice; paid billing paused (prorated) until restored |
| Legal-clarity event: any signal-seller enforcement, or Polymarket T&C counter-pressure aimed specifically at us (not at the category) | Halt new sales immediately; keep the free delayed feed; publish honest statement; paid subs get the run-out of their month |
| Signal flooding: market-maker sweeps destroy precision (alarm: > 50 alerts/day, or weekly manual audit precision collapses below the audit floor) | Tighten live rule thresholds (raise min USD / narrow age), announce change; if precision stays collapsed 2 weeks → pause paid alerts, keep free aggregates running |
| Relay sunset with failed v3 visibility | Dossiers degrade to on-chain-trail coverage (EVM-exact, ~10–13% of origins unresolved); feature-honesty notice in paid channel; consider Etherscan-paid or extra Alchemy apps before any price change |

---

## 7. First-revenue milestone plan

**Target (decided): 20 paying subscribers at $25–35/mo (~$500–700 MRR) within
~2 months of the launch post.** At $29: $580 gross → ~$555 net after Stripe
and ~$2 fixed. This mirrors the launch trigger and ladder economics in
`research/monetization.md` §Path-A.

**Evidence-readiness = all of:**

1. ≥ 150 free-tier Telegram members (the DM/directory/X funnel is converting).
2. ≥ 20 paid conversions at the $25–35 price point.
3. 4-week retention ≥ 70% (month-1 paid subs still paid in month 2 — the
   retention signal that says the dossier stream, not the launch spike,
   holds value).
4. Precision audit floor maintained (weekly manual verdict sampling; the
   verdict-benchmark method already exists and anchors expectations: Rule A
   precision was 40% on the Iran sample, 20% on the universe sample — the
   audit tracks drift, not perfection).

**Weekly review cadence (every Monday, 30 min, from Week 2):** members, paid
subs, churn, alert count, audit precision, dossier delivery latency, X
engagement. One decision per review (adjust funnel / price / thresholds).

**Relationship to the paper gate (decided; the feed is NOT gated by it).**
The 4-week paper-gate grade lands ~2026-11-14 (the live tape restarted
2026-10-14/15 pre-registered; `trajectory.csv` is built to grade the 4-week
trend, per the gate family used in `research/status.md`: PASS requires the
pre-registered statistics, not vibes). The feed does not wait for it, because
the product sells **detection + evidence**, whose value — the alert, the book
context, the funding trail — is provable at alert time regardless of whether
copying the bursts is profitable (exactly the edge-independence argued in
monetization.md, which matters doubly since the OOS copy gate already FAILED
on all 12 candidate cells: the copy edge is dead, the detection demand is
not). The gate outcome only changes what the **evidence page** says: a PASS
adds the live paper-book strip as a marketing asset (military-lane sharability:
"our paper copy book is up X% this month"); a FAIL publishes the honest
negative and strengthens the forensic framing. Either way the build proceeds;
the Nov-14 review point is a market-message decision, not a go/no-go for the
product.

---

## 8. OPEN DECISIONS (operator only)

1. **Name** — BurstDossier recommended; alternatives TrailWatch, PolyForensics, FreshTrail (§1.2).
2. **Pricing numbers** — Free / $29 / $59 defaults; confirm or move within $25–35 (tier 1) and $50–79 (tier 2).
3. **Primary channel** — Telegram per §2.1; confirm (Discord bot remains tier-2 on ≥ 15 paid subs).
4. **Start date** — Week-1 kickoff date for the implementing task.
5. **Domain** — buy or serve off the existing box; and the exact domain string (recommended only if $9-3 or the directory listing deserves a memorable URL).
6. **Free-tier delay length** — 24 h default (longer = weaker funnel; shorter = free tier too live).
