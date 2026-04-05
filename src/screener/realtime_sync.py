from __future__ import annotations

import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

from .auth import KISTokenProvider, load_config
from .kis_client import KISClient
from .market_data import load_symbols_from_file
from .storage import MongoOHLCVStore

KST = ZoneInfo("Asia/Seoul")


def _in_sync_window(now: datetime, extended_nxt: bool) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    if extended_nxt:
        return dt_time(8, 0) <= t <= dt_time(20, 0)
    return dt_time(9, 0) <= t <= dt_time(15, 30)


def _should_exit_session(now: datetime, extended_nxt: bool) -> bool:
    """End of trading window for this process (weekday)."""
    if now.weekday() >= 5:
        return True
    t = now.time()
    if extended_nxt:
        return t > dt_time(20, 0)
    return t > dt_time(15, 30)


def _should_wait_for_open(now: datetime, extended_nxt: bool) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    if extended_nxt:
        return t < dt_time(8, 0)
    return t < dt_time(9, 0)


def load_universe(path_str: str, store: MongoOHLCVStore) -> List[str]:
    path = Path(path_str)
    if path.exists():
        return load_symbols_from_file(str(path))
    return store.list_symbols()


def run_realtime_sync_loop(args) -> None:
    cfg = load_config()
    token_provider = KISTokenProvider(cfg)
    client = KISClient(cfg, token_provider, request_interval_seconds=args.request_interval)
    store = MongoOHLCVStore(cfg)
    if not store.enabled:
        print("[REALTIME] MongoDB not fully available; exiting.")
        return

    universe = load_universe(args.realtime_universe_file, store)
    if not universe:
        print("[REALTIME] No symbols; exiting.")
        return

    extended = not bool(getattr(args, "realtime_regular_only", False))
    cycle = max(30, int(getattr(args, "realtime_cycle_seconds", 120)))

    print(
        f"[REALTIME] symbols={len(universe)} extended_8_20={extended} "
        f"cycle={cycle}s file={args.realtime_universe_file}"
    )

    while True:
        now = datetime.now(KST)
        if now.weekday() >= 5:
            print("[REALTIME] weekend — exit")
            return

        if _should_exit_session(now, extended):
            print("[REALTIME] session end — exit")
            return

        if _should_wait_for_open(now, extended):
            print("[REALTIME] waiting for session open — sleep 30s")
            time.sleep(30)
            continue

        if not _in_sync_window(now, extended):
            time.sleep(5)
            continue

        trading_date = now.strftime("%Y%m%d")
        ok = 0
        err = 0
        for symbol in universe:
            try:
                snap = client.get_price_snapshot(symbol)
                store.upsert_today_from_snapshot(symbol, trading_date, snap)
                ok += 1
            except Exception:
                err += 1

        print(f"[REALTIME] {trading_date} round ok={ok} err={err} sleep={cycle}s")
        time.sleep(cycle)
