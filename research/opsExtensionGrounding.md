# ops-extension grounding (commit 2, NO PnL)

Pre-registration: commit `294da07` (the yaml syntax repair after this
commit did not touch the extension tuple, the shipped tuple, or the gate
definitions). Script: `scripts/research/opsExtensionGrounding.py`.
This is the verify-the-tuple-against-filling-realities step the
pre-registration's §4 promised: slug matching only, no PnL computed here.

## Verdict

**GATE G1 (incremental breadth) FAILS: the pre-registered extension newly
matches exactly 1 event on the already-fetched tape at
`[data, data/universe]`.**

- events scanned: 94 (173 markets + 857 universe markets, unique slugs)
- shipped-matched (the 15 keywords, 46 events): every one still matched
  with the extension in place (G5 additivity holds — the tuple is purely
  additive, no shipped behavior change)
- extension-matched: 6 events, of which 5 are ALREADY shipped-matched
  (they must be, per the pre-registration's do-not-reshoot accounting)
- **NEW-matched = 1 event / 1 episode**:
  `us-anti-cartel-ground-operation-in-mexico-by-january-31`
  (30.2M volumeUsd, 1 market)

## Why the surface is empty: the shipped 15 already cover the families

Per-keyword grounding over every event slug already in data
(NEW = events the extension reaches that the shipped 15 do not):

| extension keyword | NEW | matched-but-shipped-already |
|---|---|---|
| invasion (incl. invasion-of) | 0 | (none) |
| offensive | 0 | (none) |
| coup | 0 | none on tape |
| martial-law | 0 | none on tape |
| missile (incl. missile-test) | 0 | none on tape |
| attack (incl. attack-by) | 0 | none on tape |
| annex | 0 | none on tape |
| occupation | 0 | none on tape |
| operation | **1** | 1 (us-operation-to-capture-maduro-in-2025) |
| capture | 0 | 4 (us-operation-to-capture-maduro-in-2025, will-russia-capture-{kostyantynivka,kupiansk,pokrovsk}-by) |
| military | 0 | 1 (pakistan-military-strike-on-india-by-friday) |

The structural-verb families exist on the tape only inside named-entity
slugs the shipped filter already reaches via substring containment
(will-china-invade-taiwan, will-israel-invade-lebanon/syria,
us-operation-to-capture-maduro under venezuela/maduro,
will-russia-capture-* under russia). The invasion / invasion-of /
attack-by / missile-test keyword forms the review advocated were correct
structurally but carry no incremental surface here — the honest metric
(incremental-only) strips them out.

## NEW-matched slugs (the whole incremental surface)

| slug | markets | volumeUsd |
|---|---|---|
| us-anti-cartel-ground-operation-in-mexico-by-january-31 | 1 | 30,194,310 |

## Shipped-matched slugs (behavior unchanged; 46 events) — full list for the record

houthi-strike-on-israel-by-august-31; israel-strike-on-iran-on;
israel-strike-on-iranian-nuclear-facility-in-2024; israel-strikes-iran-by
{february-28, january-16, january-31, january-9, march-31}-2026;
israel-x-hamas-ceasefire-before-august; israel-x-hezbollah-ceasefire-by /
-in-2024; khamenei-out-as-supreme-leader-of-iran-by-{february-28,
march-31}; maduro-out-in-2025; nasrallah-remains-leader-of-hezbollah-
through-october-31; pakistan-military-strike-on-india-by-friday;
putin-out-as-president-of-russia-by-june-30; russia-x-ukraine-ceasefire
{before-july, before-october, by-april-30-2026, in-2024, in-2025};
thailand-strikes-cambodia-by-friday; trump-invokes-war-powers-against-
venezuela-by (0 volumeUsd); trump-x-ukraine-mineral-deal-signed-before-
may; us-forces-in-venezuela-by; us-next-strikes-iran-on;
us-operation-to-capture-maduro-in-2025; us-strikes-iran-by (+ -october-3);
us-strikes-yemen-by-september-30; us-x-iran-ceasefire-by /
-extended-by / -permanent-peace-deal-by; usisrael-strikes-iran-by
(0 volumeUsd); when-will-israel-announce-ceasefire;
will-china-invade-taiwan-by-june-30-2026 / in-2025;
will-israel-invade-lebanon-in-september; will-israel-invade-syria-in-2024;
will-russia-capture-{kostyantynivka, kupiansk, pokrovsk}-by;
will-the-iranian-regime-fall-by-march-31; will-the-us-invade-venezuela-
in-2025; zelenskyy-out-as-ukraine-president-before-july.

## Where that leaves the go/no-go

G1 was written in advance as a hard gate ("fewer ⇒ FAIL, extension dies as
'no incremental surface'"). The tape says FAIL: 1 new event vs the ≥5
required. Whether the one episode could ever have passed G2–G4 is the
first-look run's business only for disclosure (commit 3); the structural
finding stands on the grounding alone, and the only route left to test the
pre-registered tuple — unchanged, with no re-tuning against PnL — is the
pure OOS fetch of the never-fetched coup / martial-law /
invasion-proposition ladders the mechanism memo already sketched.
