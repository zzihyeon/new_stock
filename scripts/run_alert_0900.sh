#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

# 09:00 — screening from MongoDB (realtime sync should have updated today's bar)
python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --use-universe-file \
  --screen-mode pattern \
  --use-composite-score \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 1 \
  --mongo-ohlcv-limit 500 \
  --telegram-mode new \
  --telegram-title "[KIS Screener] 오전 모니터링 (09:00)" \
  --notify-when-empty \
  --empty-notify-message "[KIS Screener] 09:00 신규 편입 종목 없음" \
  --state-path ".cache/alert_daily_$(date +%Y%m%d).json"
