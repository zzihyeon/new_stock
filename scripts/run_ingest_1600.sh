#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

JOB_SOURCES="${JOB_SOURCES:-saramin,jobkorea}"
JOB_MAX_COMPANIES="${JOB_MAX_COMPANIES:-120}"

# 16:00 close-time collection (live API -> Mongo)
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --collect-jobs \
  --job-sources "$JOB_SOURCES" \
  --job-max-companies "$JOB_MAX_COMPANIES" \
  --collect-only \
  --batch-size 60 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0

