# ops-extension: pre-registration (written BEFORE any family PnL)

Date of writing: 2026-10-15, worktree `polycrawler2-opsExtension`, branch
`feature/opsExtension`. This document and
`configs/opsExtensionKeywords.yaml` are **commit 1** of the three-commit
contract. No family PnL number, cell return, bootstrap or sweep output was
computed, run, or read before this commit: the tuple below was derived only
from mechanism reasoning — the surviving rank-1 category-spreading path
("state-use-of-force verbs on by-date numeric ladders",
scratchpad `researchNewMarkets.md` §1.3, §2 Rank 1) plus the devil's-advocate
review constraints quoted in §1.

## 1. Constraint text carried from the review (verbatim)

- The extension must be **pre-registered, episode-name-free, structural
  verbs only**; PnL analysis never precedes the committed keyword/config.
- Evaluation is **incremental-only**: "the honest metric is extension cells
  minus identical non-extension cells' samples" — i.e. NEW matching only
  (extension matches minus the shipped 15-keyword matches). A cell over
  extension-matched-only entries is NOT the accepted metric.
- Episode-level acceptance: **"≥5 new episodes with P(>0) ≥0.90"**, with the
  threshold quoted in the review also as **"episode-level P(≥0.83)"**; we
  pre-commit to publishing per-episode P(>0) for every new episode and
  checking the family at BOTH thresholds.
- Fee/slippage stress: **per-category taker fee + 10% slippage stress.
  Disclosed-gap limitation, in writing: `fills.parquet` has no fee column;
  the shipped slippage model is a flat 50bps.** Per-category real fees
  cannot be reconstructed from the local fill tape; the stress is therefore
  a one-way +10% (1000bps) haircut recomputation, and this gap is repeated
  wherever first-look numbers appear below.
- **Ex-top-episode > 0** (leave-one-episode-out of the largest group).
- Seeds: the shipped 15 keywords remain untouched in behavior. Some words
  already match more than expected via substring match
  (`strategy.py` / `entrySweep.py`): the tokens recorded by the review as
  the `us-strikes-yemen-by`, `houthi-strike-on-israel`,
  `pakistan-military-strike-on-india`, `thailand-strikes-cambodia` families
  and the noted `antimmodation` token are ALREADY inside the shipped filter
  via the "strike"/"houthi" substrings — the extension must not re-shoot
  them inside new slugs and its accounting must subtract them.

## 2. Pre-registered extension tuple (commit 1 content)

NEW structural keywords (substring semantics, `any(k in eventSlug.lower())`):

```
invasion, offensive, coup, martial-law, missile, attack,
annex, occupation, operation, capture, military
```

Reasoning: each is a verb or predicate of "force is applied by a deadline"
on by-date numeric ladders — the only structural shape the mechanism needs.
Substring-subsumption is recorded rather than duplicated (`invasion` covers
`invasion-of`; `missile` covers `missile-test`; `military` is a superset of
the shipped `pakistan-military`; `attack` covers `attack-by`), and the two
deliberate loosening risks (`operation`, `attack`) are declared in the
config's risk register with the promised treatment: report what they catch,
never silently prune.
Names (yemen, cartel, mexico, assad, sudan, …) are excluded
(episode-name-free); `sanction` is excluded (coercion is not use-of-force).

## 3. Go / fail gates (written in advance)

Evaluator will run at `[data, data/universe]` on the full tape with the
shipped burst mechanics (imports `entrySweep` internals, no copy). All
numbers are computed on the **delta** sample set (NEW matches minus shipped
matches).

GATE G1 — incremental breadth: the extension must newly match ≥5 events
(events the shipped 15 do not match). Fewer ⇒ FAIL, extension dies as
"no incremental surface".

GATE G2 — episode-level acceptance: episodes are event-name-free collapses
of repeated ladders (same base slug phrase across dates). Requirement:
≥5 new episodes, with per-episode bootstrap P(>0) checked at both quoted
thresholds (0.83 / 0.90). Publish every new episode's exact P(>0),
including failures.

GATE G3 — ex-top-episode: leave-one-episode-out of the largest sample
group; the remaining delta family must have mean return > 0.

GATE G4 — fee/slippage stress: recompute delta-cell returns with a one-way
+10% haircut. Pass if the stressed mean stays > 0. The no-fee-column
disclosed gap is stated under every table (see §1).

GATE G5 — behavior preservation: the shipped 15's matched slug set must be
byte-identical before and after; the extension is purely additive in
`extension` + `shipped ∪ extension` form. Asserted in the grounding script.

Plus the standing falsifiers from the memo (reported, not gates for this
first look): p5 ≤ 0, H1/H2 sign split, `pnlWithoutTopEvent` analog
(page G3 covers its episode form).

## 4. Procedure after this commit

- Commit 2 (grounding, NO PnL): list all slugs at `[data, data/universe]`
  matching shipped vs shipped∪extension; report counts of NEW-matched vs
  shipped-matched slugs; verify G1 breadth and G5 additivity; mark any
  non-force positive control findings openly.
- Commit 3 (first look): `scripts/research/opsExtensionEval.py` importing
  `entrySweep` internals via importlib (no copied logic), evaluating the
  pre-registered cells at the shipped cell shape, delta-only, with
  event-level and (if available) episode-level n / retReal / p5 / P(>0),
  LOEO of the largest episode, and the +10% stressed variant. Results go to
  `research/opsExtensionFirstLook.md` with all tried cells disclosed
  including failures. No ranking tables, no winners picked.

PnL analysis never precedes this committed keyword file.
