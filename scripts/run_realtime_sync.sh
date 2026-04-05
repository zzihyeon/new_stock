#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

# Poll inquire-price into MongoDB (today's bar) on weekdays until session end.
# Default window: KST 08:00-20:00 (NXT-style extended hours; same domestic TR).
# Set REALTIME_REGULAR_ONLY=1 for KOSPI/KOSDAQ regular session only (09:00-15:30).
EXTRA=()
if [ "${REALTIME_REGULAR_ONLY:-0}" = "1" ]; then
  EXTRA+=(--realtime-regular-only)
fi

python -m src.screener \
  --loop-minutes 0 \
  --request-interval "${REALTIME_REQUEST_INTERVAL:-0.12}" \
  --realtime-sync-loop \
  --realtime-universe-file "${REALTIME_UNIVERSE_FILE:-data/universe_100b.txt}" \
  --realtime-cycle-seconds "${REALTIME_CYCLE_SECONDS:-120}" \
  "${EXTRA[@]}"
