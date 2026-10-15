"""Wait for the external on-chain pull to finish, then fire the analysis.

The order_hash burst pull (scripts/research/orderBurstOnchain.py) runs as a
long background job writing data/raw/dune/onchainBuy_*.csv — one file per
sampled day. This monitor does NOT pull: it polls the cache directory until
the PULLER'S OWN sample plan is fully cached, then runs
orderBurstOnchainAnalysis.main() in-process, teeing its log output to
logs/orderBurstAnalysis.log.

The day list is not duplicated here: it comes straight from the puller's
sampleDays() + its constants, so any change to the sampling plan keeps the
monitor in sync. Cache-complete mirrors the puller's own skip rule: a day is
done when its onchainBuy_<date>.csv exists (header-only days count — a zero
leg day is a valid pull result).

Run: uv run python scripts/research/orderBurstMonitor.py \
        [--timeout-hours 24] [--poll-seconds 300] [--per-month 2]
Cron-friendly: exits 0 after the analysis runs, 1 if the timeout expires with
days still missing (the cron log then shows how far the pull got).
"""

import argparse
import importlib.util
import sys
import time
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DUNE_DIR = ROOT / "data" / "raw" / "dune"
LOG_PATH = ROOT / "logs" / "orderBurstAnalysis.log"

_spec = importlib.util.spec_from_file_location(
    "obPuller", ROOT / "scripts" / "research" / "orderBurstOnchain.py")
PULLER = importlib.util.module_from_spec(_spec)
sys.modules["obPuller"] = PULLER
_spec.loader.exec_module(PULLER)  # sampleDays, SAMPLE_START, DUNE_DIR


def planDays(perMonth: int = 2) -> list[date]:
    """The exact days orderBurstOnchain.py pulls — imported, never restated."""
    monthsFrom = (PULLER.SAMPLE_START.year, PULLER.SAMPLE_START.month)
    return PULLER.sampleDays(monthsFrom, perMonth)


def missingDays(duneDir: Path, days: list[date]) -> list[date]:
    return [d for d in days if not (duneDir / f"onchainBuy_{d.isoformat()}.csv").exists()]


def progress(duneDir: Path, days: list[date]) -> tuple[int, int]:
    missing = missingDays(duneDir, days)
    return len(days) - len(missing), len(days)


class Tee:
    """Fan stdout writes out to the console and the analysis log."""

    def __init__(self, *streams) -> None:
        self.streams = [s for s in streams if s is not None]

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def runAnalysis(duneDir: Path, logPath: Path) -> None:
    """Call the analysis script's main() with stdout teed to the log."""
    _spec = importlib.util.spec_from_file_location(
        "orderBurstOnchainAnalysis", ROOT / "scripts" / "research" / "orderBurstOnchainAnalysis.py")
    analysis = importlib.util.module_from_spec(_spec)
    sys.modules["orderBurstOnchainAnalysis"] = analysis
    _spec.loader.exec_module(analysis)  # also loads duneOrderBurst as "dob"
    logPath.parent.mkdir(parents=True, exist_ok=True)
    argvSaved = sys.argv
    sys.argv = ["orderBurstOnchainAnalysis.py", "--dir", str(duneDir)]
    try:
        with logPath.open("a") as logFile, redirect_stdout(Tee(sys.stdout, logFile)):
            analysis.main()
    finally:
        sys.argv = argvSaved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--timeout-hours", type=float, default=24.0,
                        help="give up with exit 1 if the pull is still incomplete")
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--per-month", type=int, default=2)
    parser.add_argument("--dune-dir", default=None)
    args = parser.parse_args()

    duneDir = Path(args.dune_dir) if args.dune_dir else DUNE_DIR
    days = planDays(args.per_month)
    cached, total = progress(duneDir, days)
    print(f"sample plan: {total} days ({args.per_month}/month); {cached} already cached", flush=True)
    deadline = time.monotonic() + args.timeout_hours * 3600
    while (missing := missingDays(duneDir, days)):
        if time.monotonic() >= deadline:
            print(f"timeout after {args.timeout_hours:g}h: "
                  f"{len(missing)} days still missing "
                  f"(first {missing[0]}, last {missing[-1]})", flush=True)
            sys.exit(1)
        time.sleep(args.poll_seconds)
        cached, total = progress(duneDir, days)
        print(f"pull progress: {cached}/{total} days cached", flush=True)

    cached, total = progress(duneDir, days)
    print(f"pull complete: {cached}/{total} days cached; running analysis", flush=True)
    runAnalysis(duneDir, LOG_PATH)
    print(f"analysis done, log appended -> {LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
