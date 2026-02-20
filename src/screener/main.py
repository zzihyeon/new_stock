from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from .auth import KISTokenProvider, load_config
from .kis_client import KISClient
from .market_data import (
    build_universe_by_market_cap,
    collect_market_dataset,
    collect_market_dataset_from_store,
    load_symbols_from_csv,
    load_symbols_from_file,
)
from .report import (
    new_inclusions,
    notify_full_watchlist,
    notify_new_inclusions,
    print_console_table,
    print_top5_summary,
    read_previous_symbols,
    save_csv,
    save_current_symbols,
    save_universe_list,
)
from .screener import ScreenConfig, run_relaxed_screening, run_screening
from .storage import MongoOHLCVStore


def _load_symbol_seed() -> List[str]:
    csv_symbols = load_symbols_from_csv("data/symbols.csv")
    txt_symbols = load_symbols_from_file("data/symbols.txt")
    return sorted(set(csv_symbols + txt_symbols))


def _load_symbol_name_map(csv_path: str = "data/symbols.csv") -> Dict[str, str]:
    path = Path(csv_path)
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            name = (row.get("name") or "").strip()
            if symbol:
                out[symbol] = name
    return out


def run_once(args: argparse.Namespace) -> None:
    cfg = load_config()
    token_provider = KISTokenProvider(cfg)
    client = KISClient(cfg, token_provider, request_interval_seconds=args.request_interval)
    store = MongoOHLCVStore(cfg)
    print(f"[MONGO] enabled={store.enabled}")

    symbol_seed = args.symbols if args.symbols else _load_symbol_seed()
    symbol_name_map = _load_symbol_name_map()
    if not symbol_seed:
        print("No symbols found. Add data/symbols.txt or pass --symbols.")
        return

    if args.data_source == "mongo":
        if args.symbols:
            universe = list(args.symbols)
        else:
            if args.use_universe_file and Path("data/universe_100b.txt").exists():
                universe = load_symbols_from_file("data/universe_100b.txt")
            else:
                universe = store.list_symbols()
        print(f"Universe size from stored data: {len(universe)}")
        dataset = collect_market_dataset_from_store(store, universe, limit=args.mongo_ohlcv_limit)
    else:
        universe = build_universe_by_market_cap(
            client,
            symbols=symbol_seed,
            min_market_cap_won=args.min_market_cap,
            batch_size=args.batch_size,
        )
        universe_path = save_universe_list(universe)
        print(f"Universe size after market-cap filter: {len(universe)}")
        print(f"Universe list saved: {universe_path}")
        dataset = collect_market_dataset(client, universe, batch_size=args.batch_size, store=store)

    if args.collect_only:
        print("[MODE] collect-only run completed.")
        return
    dataset, ref_date = _filter_dataset_by_recency(dataset, args.max_date_lag_days)
    print(f"[TIME] reference_date={ref_date}, max_date_lag_days={args.max_date_lag_days}, eligible={len(dataset)}")

    base_cfg = ScreenConfig(
        min_market_cap_won=args.min_market_cap,
        d0_vol_multiple=args.d0_vol_multiple,
        d1_volume_drop_ratio=args.d1_drop_ratio,
        min_current_volume=args.min_current_volume,
        min_recent_n_volume=args.min_recent_n_volume,
        recent_volume_lookback_days=args.recent_volume_lookback_days,
        d0_tv_percentile_min=args.d0_tv_percentile_min,
        d0_surge_require_both=args.d0_require_both,
        pattern_a_pullback_days=args.pattern_a_pullback_days,
        max_one_day_rise_pct=args.max_one_day_rise_pct,
        max_three_day_rise_pct=args.max_three_day_rise_pct,
        min_pullback_from_recent_high_pct=args.min_pullback_from_recent_high_pct,
        max_pullback_from_recent_high_pct=args.max_pullback_from_recent_high_pct,
    )
    tuned_cfg, results = tune_screening_params(dataset, base_cfg, args.target_count, args.debug_symbols)
    if len(results) < args.target_count:
        relaxed = run_relaxed_screening(
            dataset,
            tuned_cfg,
            target_count=args.target_count - len(results),
            exclude_symbols=set(row["symbol"] for row in results),
        )
        results.extend(relaxed)
    print(
        "[TUNE] "
        f"d0_vol_multiple={tuned_cfg.d0_vol_multiple}, "
        f"d1_drop_ratio={tuned_cfg.d1_volume_drop_ratio}, "
        f"min_current_volume={tuned_cfg.min_current_volume}, "
        f"recent_{tuned_cfg.recent_volume_lookback_days}d_min_volume={tuned_cfg.min_recent_n_volume}, "
        f"d0_tv_percentile_min={tuned_cfg.d0_tv_percentile_min}, "
        f"pattern_a_pullback_days={tuned_cfg.pattern_a_pullback_days}, "
        f"result_count={len(results)}"
    )
    for row in results:
        row["name"] = symbol_name_map.get(row["symbol"], row["symbol"])

    print_console_table(results)
    report_path = save_csv(results)
    if report_path:
        print(f"CSV saved: {report_path}")
    else:
        print("No screening result: report file not created.")
    print_top5_summary(results)

    old_symbols = read_previous_symbols(args.state_path)
    newly_included = new_inclusions(results, old_symbols)
    if args.telegram_mode == "full":
        notify_full_watchlist(
            results,
            cfg.telegram_bot_token,
            cfg.telegram_chat_id,
            title=args.telegram_title or "[KIS Screener] Watchlist",
        )
        print(f"Telegram sent full watchlist: {len(results)}")
    else:
        notify_new_inclusions(newly_included, cfg.telegram_bot_token, cfg.telegram_chat_id)
        if newly_included:
            print(f"Telegram notified for new inclusions: {len(newly_included)}")
        else:
            print("No new inclusion vs previous run.")

    save_current_symbols(set(row["symbol"] for row in results), args.state_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KIS domestic stock screener")
    parser.add_argument("--symbols", nargs="*", help="Explicit symbol list for debug or focused run")
    parser.add_argument("--data-source", choices=["live", "mongo"], default="live")
    parser.add_argument("--mongo-ohlcv-limit", type=int, default=500)
    parser.add_argument("--use-universe-file", action="store_true", help="Use data/universe_100b.txt in mongo mode")
    parser.add_argument("--collect-only", action="store_true", help="Only collect/update data without screening outputs")
    parser.add_argument("--telegram-mode", choices=["new", "full"], default="new")
    parser.add_argument("--telegram-title", default="")
    parser.add_argument("--state-path", default=".cache/last_candidates.json")
    parser.add_argument("--debug-symbols", nargs="*", default=[], help="Debug log output for specific symbols")
    parser.add_argument("--min-market-cap", type=int, default=100_000_000_000)
    parser.add_argument("--d0-vol-multiple", type=float, default=1.2)
    parser.add_argument("--d1-drop-ratio", type=float, default=0.3)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--request-interval", type=float, default=0.12)
    parser.add_argument("--min-current-volume", type=int, default=1_000_000)
    parser.add_argument("--min-recent-n-volume", type=int, default=1_000_000)
    parser.add_argument("--recent-volume-lookback-days", type=int, default=5)
    parser.add_argument("--d0-tv-percentile-min", type=float, default=45.0)
    parser.add_argument("--d0-require-both", action="store_true", help="Require both vol surge and trading-value percentile surge")
    parser.add_argument("--pattern-a-pullback-days", type=int, default=6)
    parser.add_argument("--target-count", type=int, default=20, help="Target number of screening results")
    parser.add_argument("--max-one-day-rise-pct", type=float, default=8.0)
    parser.add_argument("--max-three-day-rise-pct", type=float, default=15.0)
    parser.add_argument("--min-pullback-from-recent-high-pct", type=float, default=1.0)
    parser.add_argument("--max-pullback-from-recent-high-pct", type=float, default=18.0)
    parser.add_argument(
        "--max-date-lag-days",
        type=int,
        default=0,
        help="Only include symbols whose latest bar date is within this lag from reference latest date.",
    )
    parser.add_argument(
        "--loop-minutes",
        type=int,
        default=24 * 60,
        help="Repeat run every N minutes (default: 1440 = once per day). Use 0 for one-shot.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.loop_minutes <= 0:
        run_once(args)
        return

    while True:
        try:
            run_once(args)
        except Exception as exc:
            print(f"[ERROR] periodic run failed: {exc}")
        sleep_seconds = max(args.loop_minutes, 1) * 60
        print(f"Sleeping for {sleep_seconds} seconds before next screening...")
        time.sleep(sleep_seconds)


def tune_screening_params(
    dataset: Dict[str, Dict],
    base_cfg: ScreenConfig,
    target_count: int,
    debug_symbols: List[str],
) -> Tuple[ScreenConfig, List[Dict]]:
    if target_count <= 0:
        results = run_screening(dataset, base_cfg, debug_symbols=debug_symbols)
        return base_cfg, results

    candidate_pairs = [
        (1.5, 0.50, 60.0, 3),
        (1.3, 0.40, 45.0, 4),
        (1.2, 0.35, 40.0, 5),
        (1.1, 0.30, 35.0, 6),
        (1.0, 0.25, 30.0, 6),
        (0.9, 0.20, 25.0, 7),
        (0.85, 0.15, 20.0, 7),
        (0.8, 0.10, 15.0, 8),
        (0.75, 0.05, 10.0, 8),
        (0.7, 0.00, 5.0, 8),
        (0.65, -0.10, 0.0, 9),
        (0.6, -0.20, 0.0, 10),
    ]

    best_cfg = base_cfg
    best_results = run_screening(dataset, base_cfg, debug_symbols=debug_symbols)
    best_gap = abs(len(best_results) - target_count)
    max_count_cfg = best_cfg
    max_count_results = best_results

    for d0_mult, d1_drop, tv_min, pullback_days in candidate_pairs:
        trial_cfg = ScreenConfig(
            min_market_cap_won=base_cfg.min_market_cap_won,
            d0_vol_multiple=d0_mult,
            d1_volume_drop_ratio=d1_drop,
            min_current_volume=base_cfg.min_current_volume,
            min_recent_n_volume=base_cfg.min_recent_n_volume,
            recent_volume_lookback_days=base_cfg.recent_volume_lookback_days,
            d0_tv_percentile_min=tv_min,
            d0_surge_require_both=base_cfg.d0_surge_require_both,
            pattern_a_pullback_days=pullback_days,
            allow_b_days_after_d0=base_cfg.allow_b_days_after_d0,
            max_one_day_rise_pct=base_cfg.max_one_day_rise_pct,
            max_three_day_rise_pct=base_cfg.max_three_day_rise_pct,
            min_pullback_from_recent_high_pct=base_cfg.min_pullback_from_recent_high_pct,
            max_pullback_from_recent_high_pct=base_cfg.max_pullback_from_recent_high_pct,
            max_candidates=base_cfg.max_candidates,
        )
        trial_results = run_screening(dataset, trial_cfg, debug_symbols=debug_symbols)
        gap = abs(len(trial_results) - target_count)
        if len(trial_results) > len(max_count_results):
            max_count_cfg = trial_cfg
            max_count_results = trial_results
        if gap < best_gap:
            best_cfg = trial_cfg
            best_results = trial_results
            best_gap = gap
        elif gap == best_gap and len(trial_results) > len(best_results):
            best_cfg = trial_cfg
            best_results = trial_results
            best_gap = gap

    if len(best_results) < target_count and len(max_count_results) > len(best_results):
        best_cfg = max_count_cfg
        best_results = max_count_results

    return best_cfg, best_results


def _filter_dataset_by_recency(dataset: Dict[str, Dict], max_date_lag_days: int) -> Tuple[Dict[str, Dict], str]:
    latest_dates: List[str] = []
    for payload in dataset.values():
        ohlcv = payload.get("ohlcv", [])
        if ohlcv:
            latest_dates.append(str(ohlcv[-1].get("date", "")))

    if not latest_dates:
        return dataset, ""

    ref_date = max(latest_dates)
    try:
        ref_dt = datetime.strptime(ref_date, "%Y%m%d")
    except ValueError:
        return dataset, ref_date

    filtered: Dict[str, Dict] = {}
    for symbol, payload in dataset.items():
        ohlcv = payload.get("ohlcv", [])
        if not ohlcv:
            continue
        d = str(ohlcv[-1].get("date", ""))
        try:
            dt = datetime.strptime(d, "%Y%m%d")
        except ValueError:
            continue
        if dt >= ref_dt - timedelta(days=max(max_date_lag_days, 0)):
            filtered[symbol] = payload
    return filtered, ref_date


if __name__ == "__main__":
    main()

