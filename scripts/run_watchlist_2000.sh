#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

# 20:00 next-day watchlist from stored data
python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0 \
  --telegram-mode full \
  --telegram-title "[KIS Screener] Next-day Watchlist (20:00)" \
  --state-path ".cache/nextday_watchlist_state.json"

