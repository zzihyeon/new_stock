#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

# 16:00 close-time collection (live API -> Mongo)
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --collect-only \
  --batch-size 60 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0

