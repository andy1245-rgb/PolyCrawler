"""Rebuild data/live: drop replayed rows, keep the honest history.

Approved by the operator 2026-11-10. Archival, not deletion: every file is copied
to data/live/archive-2026-11-10/ before anything is touched, and a second copy is
taken outside the repository.

The filter keeps rows whose alertTs predates the replay window (2026-10-18). The
header of each kept book is preserved exactly, so a legacy book keeps its 13/13/15
columns and writtenTs stays withheld rather than being written as a blank -- the
old rows are honest about not knowing when they were written.
"""

import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

LIVE = Path("/home/andrew/polycrawler2/data/live")
CUTOFF = "2026-10-18"
BOOKS = ("signals.csv", "signalsLane2.csv", "signalsLane3.csv")
STAMP = "2026-11-10"
ARCHIVE = LIVE / f"archive-{STAMP}"

# The derived books are computed from the signals, so they are rebuilt downstream
# rather than edited here.
DERIVED = ("execStamps.csv", "laneCloses.csv", "laneMarks.csv",
           "openPositions.csv", "trajectory.csv")


def main() -> int:
    outside = Path(f"/home/andrew/polycrawler2-live-backup-{datetime.now():%Y%m%dT%H%M%S}")
    outside.mkdir(parents=True, exist_ok=False)
    for name in BOOKS + DERIVED:
        src = LIVE / name
        if src.exists():
            shutil.copy2(src, outside / name)
    print(f"backup outside the repo: {outside}")

    ARCHIVE.mkdir(exist_ok=True)
    for name in BOOKS + DERIVED:
        src = LIVE / name
        if src.exists():
            shutil.copy2(src, ARCHIVE / name)
    print(f"archive inside the repo: {ARCHIVE}")

    for name in BOOKS:
        path = LIVE / name
        with path.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            print(f"{name}: empty, left alone")
            continue
        fields = list(rows[0])
        keep = [r for r in rows if r["alertTs"][:10] < CUTOFF]
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(keep)
        print(f"{name}: kept {len(keep)} of {len(rows)}  (header unchanged, {len(fields)} columns)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
