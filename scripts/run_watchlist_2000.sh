#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

JOB_SOURCES="${JOB_SOURCES:-saramin,jobkorea}"
JOB_MAX_COMPANIES="${JOB_MAX_COMPANIES:-120}"

# 20:00 next-day watchlist from stored data
python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --collect-jobs \
  --job-sources "$JOB_SOURCES" \
  --job-max-companies "$JOB_MAX_COMPANIES" \
  --use-composite-score \
  --target-count 7 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0 \
  --telegram-mode full \
  --telegram-title "[KIS Screener] Next-day Watchlist (20:00)" \
  --state-path ".cache/nextday_watchlist_state.json"

