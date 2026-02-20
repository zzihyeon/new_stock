#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"

source ".venv/bin/activate"

# 1) Live collection + screening at market close
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --batch-size 60 \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0

# 2) Stored-data based screening snapshot for analysis/report
python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0

