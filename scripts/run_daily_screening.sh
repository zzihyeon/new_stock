#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"

source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

# 1) Live collection + screening at market close
python -m src.screener \
  --loop-minutes 0 \
  --data-source live \
  --collect-jobs \
  --job-sources "saramin,jobkorea" \
  --job-max-companies 120 \
  --use-composite-score \
  --batch-size 60 \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0

# 2) Stored-data screening in parallel:
#    - existing pattern mode
#    - new dart-score mode
python -m src.screener \
  --loop-minutes 0 \
  --screen-mode pattern \
  --data-source mongo \
  --use-composite-score \
  --target-count 20 \
  --min-current-volume 1000000 \
  --max-date-lag-days 0 &
pid_pattern=$!

python -m src.screener \
  --loop-minutes 0 \
  --screen-mode dart-score \
  --data-source mongo \
  --target-count 20 \
  --min-market-cap 100000000000 \
  --max-date-lag-days 0 &
pid_dart=$!

wait "$pid_pattern"
wait "$pid_dart"

