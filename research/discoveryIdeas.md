# Discovery ideas: rolling monthly test

Script: `scripts/research/discoveryIdeas.py`. Data: `data/` (Iran and Venezuela) plus `data/universe/` (72 events), 3.9M buy entries.

**Method.** At the start of each month from Oct 2024 to Sep 2026, flag accounts using only bets placed and markets resolved before that month. Then copy every buy those accounts make during the month: **$100 at the insider's own price**, settled at resolution. Account age and market count come from our own fills, not the activity API, so the age filter is looser than real step 1.

Ideas:

- **A — fresh longshot:** account ≤ 14 days old at the bet, ≤ 15 markets, won ≥ $1k at ≤ 0.30. This is the current rule.
- **B — repeat winner:** ≥ 2 winning longshots (≤ 0.35, ≥ $500) in ≥ 2 different events, and a longshot win rate ≥ 50%.
- **C — late and informed:** won a ≥ $1k bet at ≤ 0.30, placed ≤ 48h before resolution.
- **D — high past return:** ≥ 3 resolved bets of ≥ $500 with dollar-weighted return ≥ +100%.
- **E — concentrated:** ≥ 80% of the account's USD in one event, and won a ≥ $1k bet at ≤ 0.30. No age limit.
- **Baseline:** any account's buy of ≥ $1k at ≤ 0.30.

| Set | Copies | Events | Events in profit | Win rate | Mean return | Median event return | Return without top event | Copies excl. Iran and Venezuela | Return excl. Iran and Venezuela |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 14,032 | 78 | 20 | 29% | +70% | −99% | +38% | 5,575 | −45% |
| A all | 7,466 | 75 | 31 | 33% | +12% | −33% | −40% | 5,725 | −41% |
| A ≤ 0.35 | 5,020 | 61 | 17 | 14% | +10% | −100% | −64% | 4,064 | −64% |
| B all | 20,543 | 71 | 26 | 48% | +13% | −15% | −18% | 13,933 | −19% |
| B ≤ 0.35 | 8,369 | 65 | 20 | 14% | +35% | −100% | −43% | 6,214 | −45% |
| C all | 25,376 | 55 | 13 | 59% | +40% | −19% | −19% | 13,564 | −21% |
| C ≤ 0.35 | 8,673 | 48 | 8 | 22% | +120% | −100% | −60% | 4,435 | −69% |
| D all | 10,918 | 73 | 19 | 25% | −17% | −56% | −55% | 7,425 | −60% |
| D ≤ 0.35 | 7,999 | 68 | 15 | 9% | −28% | −100% | −73% | 6,067 | −78% |
| E all | 14,037 | 70 | 30 | 49% | +26% | −14% | −13% | 7,356 | **−9%** |
| E ≤ 0.35 | 5,930 | 67 | 18 | 22% | +50% | −100% | −41% | 3,776 | −34% |

## Takeaways

- **Nothing makes money outside Iran and Venezuela.** The best is E (concentrated) at −9%. The current rule A, at −41%, is about the same as the baseline of copying anyone's big longshot (−45%).
- **Every positive mean comes from a few huge longshot payouts in the Iran events.**
- **The ≤ 0.35 entry filter hurts outside Iran.** Most copied longshots lose, which is the usual favorite–longshot bias.
- **Concentration (E) and repeat winning (B) are the least bad.** Both select for focus or skill rather than luck on one ticket.
- **The manual review (`sampleReview.md`) shows why A is noisy:** about half of the flags are date-ladder speculators. Next filters to test are ladder precision, co-trade clusters and the recreational-noise tell.
- **Caveats:** copying at the insider's own price is optimistic, and outside Iran and Venezuela our account ages are only lower bounds.
