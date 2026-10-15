#!/bin/sh
# PolyCrawler2 catch-up: self-heal the watcher + backfill a missed daily report.
# Designed to run from system cron every 10 min and at reboot, so a day where
# the PC (or Command Code) was off at 9:23 is still processed at the next boot.
PATH=/home/andrew/.local/bin:/usr/local/bin:/usr/bin:/bin

cd /home/andrew/polycrawler2 || exit 1

# 1. Watcher self-heal
if ! pgrep -f "liveWatcher.py" >/dev/null 2>&1; then
    nohup uv run python scripts/liveWatcher.py >> logs/liveWatcher.log 2>&1 &
    echo "$(date '+%F %T') watcher was down, restarted"
fi

# 2. Daily report backfill (marker file makes it once-per-day; paperPnl is idempotent)
TODAY=$(date +%F)
if [ "$(cat logs/lastDailyReport 2>/dev/null)" != "$TODAY" ]; then
    echo "$(date '+%F %T') running daily paper report" >> logs/dailyReport.log
    uv run python scripts/paperPnl.py >> logs/dailyReport.log 2>&1
    uv run python scripts/paperMarkToMarket.py >> logs/dailyReport.log 2>&1
    echo "$TODAY" > logs/lastDailyReport
    echo "$(date '+%F %T') daily report done" >> logs/dailyReport.log
fi
