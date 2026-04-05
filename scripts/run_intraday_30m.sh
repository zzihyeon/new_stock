#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

TODAY_STATE=".cache/intraday_watchlist_$(date +%Y%m%d).json"
JOB_SOURCES="${JOB_SOURCES:-saramin,jobkorea}"
JOB_MAX_COMPANIES="${JOB_MAX_COMPANIES:-80}"

# 09:00~ every 30m, live API based new-entrant check
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --collect-jobs \
  --job-sources "$JOB_SOURCES" \
  --job-max-companies "$JOB_MAX_COMPANIES" \
  --use-composite-score \
  --target-count 7 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0 \
  --telegram-mode new \
  --telegram-market-hours-only \
  --notify-when-empty \
  --empty-notify-message "[KIS Screener] 현재 신규 없음 (정규장 기준)" \
  --state-path "$TODAY_STATE"

