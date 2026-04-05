#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/Users/ji-hyeonyu/stock}"
cd "$PROJECT_DIR"
source ".venv/bin/activate"
export PYTHONUNBUFFERED=1

DART_SQLITE_PATH="${DART_SQLITE_PATH:-dart/dart_cache.sqlite}"

# One-time DART SQLite -> Mongo migration only.
# Uses a single symbol seed to minimize unrelated data loading.
python -m src.screener \
  --loop-minutes 0 \
  --data-source mongo \
  --symbols 005930 \
  --collect-only \
  --migrate-dart-sqlite-path "$DART_SQLITE_PATH" \
  --skip-telegram

