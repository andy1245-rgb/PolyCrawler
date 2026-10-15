"""Wait for the external on-chain pull to finish, then fire the analysis.

The order_hash burst pull (scripts/research/orderBurstOnchain.py) runs as a
long background job writing data/raw/dune/onchainBuy_*.csv — one file per
sampled day. This monitor does NOT pull: it polls the cache directory until
the puller's sample plan is fully cached, then runs
orderBurstOnchainAnalysis.main(dir_=...) in-process, teeing its log output to
logs/orderBurstAnalysis.log.

The day list is not duplicated here: it comes from the plan file the puller
writes at startup (data/raw/dune/samplePlan.json), or — while the file does
not exist yet — the puller's own sampleDays() + its constants, so any change
to the sampling plan keeps the monitor in sync. Days that have not yet
elapsed are excluded: "complete" means all OBSERVED days are cached, never a
future day (which would make the monitor time out forever mid-month). A day
is done when its onchainBuy_<date>.csv exists (header-only days count — a
zero-leg day is a valid pull result).

Run-once guard: an flock on data/raw/dune/orderBurstMonitor.lock keeps two
monitor instances from racing each other; if the lock is held the monitor
exits 0 with a one-line note. After the analysis fires, a sentinel
logs/orderBurstAnalysis_<planHash>.done (planHash = short digest of the
sorted plan) marks the plan done, so re-runs exit 0 immediately ("already
fired") instead of rebuilding the whole analysis every cron tick.

Run: uv run python scripts/research/orderBurstMonitor.py \
        [--timeout-hours 24] [--poll-seconds 300] [--per-month 2]
Cron-friendly: exits 0 after the analysis runs (or if it already fired /
another instance is running), 1 if the timeout expires with days still
missing (the cron log then shows how far the pull got).
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import sys
import time
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "logs" / "orderBurstAnalysis.log"

_spec = importlib.util.spec_from_file_location(
    "obPuller", ROOT / "scripts" / "research" / "orderBurstOnchain.py")
PULLER = importlib.util.module_from_spec(_spec)
sys.modules["obPuller"] = PULLER
_spec.loader.exec_module(PULLER)  # sampleDays, SAMPLE_START, PER_MONTH, DUNE_DIR, PLAN_PATH

# DUNE_DIR / plan path come from the puller, never redefined here.
DUNE_DIR = PULLER.DUNE_DIR
PLAN_PATH = PULLER.PLAN_PATH
LOCK_PATH = DUNE_DIR / "orderBurstMonitor.lock"


def samplePlanDays(perMonth: int = PULLER.PER_MONTH) -> list[date]:
    """The puller's full day plan, unfiltered: the plan file it wrote at
    startup when that exists, else its own sampleDays() plan (imported,
    never restated)."""
    if PLAN_PATH.exists():
        return [date.fromisoformat(s) for s in json.loads(PLAN_PATH.read_text())]
    monthsFrom = (PULLER.SAMPLE_START.year, PULLER.SAMPLE_START.month)
    return PULLER.sampleDays(monthsFrom, perMonth)


def planDays(perMonth: int = PULLER.PER_MONTH) -> list[date]:
    """Days the monitor waits for: the puller's plan minus days that have not
    yet elapsed (today and later are dropped) — the monitor must never sit
    waiting on a future day's cache."""
    today = datetime.now(timezone.utc).date()
    return [d for d in samplePlanDays(perMonth) if d < today]


def planHash(days: list[date]) -> str:
    """Short digest of the sorted plan; joins the completion sentinel name."""
    text = "\n".join(d.isoformat() for d in sorted(days))
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def missingDays(duneDir: Path, days: list[date]) -> list[date]:
    return [d for d in days if not (duneDir / f"onchainBuy_{d.isoformat()}.csv").exists()]


def progress(duneDir: Path, days: list[date]) -> tuple[int, int]:
    missing = missingDays(duneDir, days)
    return len(days) - len(missing), len(days)


def acquireRunOnceGuard(path: Path = LOCK_PATH):
    """flock the lock file for the process lifetime; None if another monitor
    instance already holds it (keep the file handle open — the lock dies with
    the process)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


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
    """Call the analysis script's main(dir_=...) with stdout teed to the log."""
    _spec = importlib.util.spec_from_file_location(
        "orderBurstOnchainAnalysis", ROOT / "scripts" / "research" / "orderBurstOnchainAnalysis.py")
    analysis = importlib.util.module_from_spec(_spec)
    sys.modules["orderBurstOnchainAnalysis"] = analysis
    _spec.loader.exec_module(analysis)  # also loads duneOrderBurst as "dob"
    logPath.parent.mkdir(parents=True, exist_ok=True)
    with logPath.open("a") as logFile:
        started = datetime.now(timezone.utc).isoformat()
        logFile.write(f"=== orderBurstAnalysis started {started} ===\n")
        logFile.flush()
        with redirect_stdout(Tee(sys.stdout, logFile)):
            analysis.main(dir_=duneDir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--timeout-hours", type=float, default=24.0,
                        help="give up with exit 1 if the pull is still incomplete")
    parser.add_argument("--poll-seconds", type=int, default=300)
    parser.add_argument("--per-month", type=int, default=PULLER.PER_MONTH,
                        help=f"only used while {PLAN_PATH.name} is absent")
    parser.add_argument("--dune-dir", default=None)
    args = parser.parse_args()

    guard = acquireRunOnceGuard()
    if guard is None:
        print("orderBurstMonitor: another instance holds "
              f"{LOCK_PATH}; exiting", flush=True)
        return

    plan = samplePlanDays(args.per_month)   # full plan -> sentinel name
    days = planDays(args.per_month)          # elapsed days -> what we wait on
    sentinel = LOG_PATH.parent / f"orderBurstAnalysis_{planHash(plan)}.done"
    if sentinel.exists():
        print(f"orderBurstMonitor: plan {planHash(plan)} already fired "
              f"({sentinel.name}); exiting", flush=True)
        return

    duneDir = Path(args.dune_dir) if args.dune_dir else DUNE_DIR
    cached, total = progress(duneDir, days)
    print(f"sample plan: {total} observed days ({args.per_month}/month); "
          f"{cached} already cached", flush=True)
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
    print(f"pull complete: {cached}/{total} cached; running analysis", flush=True)
    runAnalysis(duneDir, LOG_PATH)
    sentinel.write_text(datetime.now(timezone.utc).isoformat() + "\n")
    print(f"analysis done, log appended -> {LOG_PATH} "
          f"(sentinel {sentinel.name})", flush=True)


if __name__ == "__main__":
    main()
