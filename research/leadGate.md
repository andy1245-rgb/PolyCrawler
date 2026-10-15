# Copy-time lead gate: testing the timing signal from the verdict benchmarks

Scripts: `scripts/research/copyLeadGate.py`, `leadGateRobustness.py`,
`leadGateMonthly.py`, plus `verdictBenchmark.py` and the two verdict label
files (`sampleVerdicts.csv`, `universeVerdicts.csv`). Data: `data/` +
`data/universe/` (3.9M buy entries). Copies are $100 at the account's own
price, settled at resolution, monthly rolling Oct 2024 – Sep 2026.

## 1. The verdict benchmarks (ground truth now machine-readable)

Two 20-account manual-verdict samples, both reproducible by
`verdictBenchmark.py`:

- **Iran sample (seed=7)**: 4 insiders (the six-wallet co-trade cluster),
  4 likely insiders, 8 speculators. Rule A precision 40%.
- **Universe sample (seed=8, from the 89 flagged on 72 events)**: 4
  insider/likely (all ZachXBT/Axiom), 6 possible, 10 speculators. Rule A
  precision 20%.

**Lead time is the clean separator in both samples.** Every positive in the
universe sample entered ≤ 68h before resolution; every speculator ≥ 544h.
Gate `leadHours ≤ 168 + marketsTraded ≤ 3`: 100% precision, 100% recall
(loose class). Caveats: all 4 positives come from one event (Axiom), and in
the Iran sample the co-trade insiders trade 5–12 markets, so "few markets"
is not a universal insider shape — one-shot and cluster-member are disjoint.

## 2. Copy-time lead gate (the new, honest test)

The earlier failure ("A + bet placed ≤ 72h before resolution", −50%) gated
the *flag* bet with hindsight. The new test gates the **bet we copy, at copy
time** — observable in real time, since the market's resolution date is known
when the bet lands.

| Copy gate (flag = rule A) | n | Win rate | Return | ex-Iran/Venezuela | w/o top event |
|---|---:|---:|---:|---:|---:|
| no gate | 7,466 | 33% | +12% | −41% | −40% |
| ≤7d + ≥$1k | 455 | 72% | +55% | +0.2% | +0.8% |
| ≤3d + ≥$1k | 276 | 80% | +44% | +5.1% | +5.0% |
| ≤7d + ≥$5k | 195 | 82% | +36% | +2.2% | +3.7% |
| ≤3d + ≥$5k | 139 | 86% | +29% | +3.6% | +3.4% |
| ≤24h + ≥$5k | 67 | 90% | +16% | +2.1% | +3.9% |

First time anything is non-negative ex-Iran/Venezuela. Then robustness:

- **Time half splits the sign.** ex-IV return is positive Oct'24–Jun'25,
  negative Jun'25–Oct'26 (lead3d big1k: +13.8% → −20.6%).
- **Event bootstrap P(>0) = 46–77%.** Best (lead3d big5k): 77%, p5 −4.7%,
  p95 +12.5%.
- **Slippage kills it.** Copying at 5% worse than the insider's price puts
  every variant at ≈0 or below; 20% slippage → −12% to −17%.
- **Concentration.** ex-IV total PnL is $37–$837 and top-3 events exceed
  100% of it.

## 3. Why it fails (leadGateMonthly.py)

The ≤72h big-≥$5k copies have **average price 0.87–0.92, mostly 0.95+**.
A flagged account's large late bet is usually a near-certain favorite (Fed
decisions, TikTok ban, award shows) — the copied edge is cents of favorite
drift, which slippage eats. The H1 profit came from exactly two genuinely
informed late longshots (Assad-out at 0.83, Israel-invade-Lebanon at 0.62);
H2 contained none outside Iran, so the rest is noise on favorites.

## 4. Conclusions

1. **The lead gate is a real *discovery* improvement** — it separates
   insiders from speculators in two independent labeled samples and is
   computable at flag time (the flag bet's lead is known only in hindsight,
   but the *copy* bet's lead is known in real time). Add a lead-time signal
   to step 1 / cluster scoring, but do not expect it to make copy-trading
   profitable by itself.
2. **As a strategy, copying flagged accounts' late bets is dead**: after
   5% slippage everything is ≤ 0 ex-Iran. The profitable copies are rare
   informed longshots inside military/geopolitical events — the same
   conclusion as every prior experiment.
3. The standing project conclusion holds: the only reliable insider edge on
   Polymarket in this universe is event-specific (military strikes, exposed
   insider cases like Axiom). The path forward remains the category-specific
   test in `freshAccountSignal.md` §"Next test".

## 5. Shipped: `maxFlagLeadHours` hard gate in discovery (2026-10-08)

The lead-time signal is now in the package: `DiscoveryConfig.maxFlagLeadHours`
(default 168, `None` disables) gates step-1 flags as a hard requirement in
both `discovery.py` and `discovery/flagging.py`. Design note: it must be a
gate, not a fifth signal — on date-ladder events (Iran) speculators also buy
the winning date late, and the extra signal only inflated the pool
(236 → 405). As a gate, verified on both labeled 20-account samples with the
package pipeline (`pc2 discover --step1-only`):

| Sample | Flagged before | Flagged after | Precision (loose) | Recall |
|---|---:|---:|---|---|
| Iran (seed=7) | 236 | 151 | 40% → 57% | 8/8 |
| Universe (seed=8) | 89 | 36 | 20% → 67% | 4/4, zero speculators flagged |
