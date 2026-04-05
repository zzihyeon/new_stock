#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

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
  --telegram-title "[KIS Screener] 점심 모니터링 (13:00)" \
  --notify-when-empty \
  --empty-notify-message "[KIS Screener] 13:00 신규 편입 종목 없음" \
  --state-path ".cache/alert_daily_$(date +%Y%m%d).json"
