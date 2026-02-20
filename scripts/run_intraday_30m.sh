#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

TODAY_STATE=".cache/intraday_watchlist_$(date +%Y%m%d).json"

# 09:00~ every 30m, live API based new-entrant check
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0 \
  --telegram-mode new \
  --state-path "$TODAY_STATE"

