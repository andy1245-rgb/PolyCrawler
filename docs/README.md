# docs

Long-form records that back the claims on the front page: what a component actually records, what
was measured, and what is still wrong with it. Reference material, not instructions — nothing here
is needed to run the tool.

| Document | What it records |
|---|---|
| [paper-lane-records.md](paper-lane-records.md) | The paper-lane books: why `alertTs` (event time) and `writtenTs` (write time) are separate columns, how a position's horizon is anchored, what the backtester does with a missing price, how the dedupe key had already collapsed 72 rows to 22, and which rows in the live books are still untrustworthy — with the rebuild that would clear them. |

## Related documents elsewhere in the repo

| Document | What it records |
|---|---|
| [`../SPEC.md`](../SPEC.md) | the v0.2 draft the code was built against |
| [`../SPEC-DIVERGENCES.md`](../SPEC-DIVERGENCES.md) | where the code moved away from that draft, and which side should change |
| [`../research/`](../research/) | one document per study, each with its numbers and its verdict |
