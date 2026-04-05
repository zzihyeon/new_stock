#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

JOB_SOURCES="${JOB_SOURCES:-saramin,jobkorea}"
JOB_MAX_COMPANIES="${JOB_MAX_COMPANIES:-120}"

python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --use-universe-file \
  --screen-mode pattern \
  --collect-jobs \
  --job-sources "$JOB_SOURCES" \
  --job-max-companies "$JOB_MAX_COMPANIES" \
  --use-composite-score \
  --target-count 7 \
  --min-current-volume 1000000 \
  --max-date-lag-days 1 \
  --mongo-ohlcv-limit 500 \
  --telegram-mode full \
  --telegram-title "[KIS Screener] 다음날 관심종목 (20:00)"

python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --use-universe-file \
  --screen-mode dart-score \
  --target-count 7 \
  --min-market-cap 100000000000 \
  --max-date-lag-days 1 \
  --mongo-ohlcv-limit 500 \
  --telegram-mode full \
  --telegram-title "[KIS Screener] DART 스코어 종목 (영업이익과 직원 수 증가 대비 주가 낮음) (20:00)"
