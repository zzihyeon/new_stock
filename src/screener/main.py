from __future__ import annotations

import argparse
import csv
import io
import json
import time
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, List, Set, Tuple
from zoneinfo import ZoneInfo

from .auth import KISTokenProvider, load_config
from .dart_migration import migrate_dart_sqlite_to_mongo
from .jobs_collector import collect_jobs_and_update_features
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
    send_telegram,
)
from .screener import ScreenConfig, run_dart_score_screening, run_relaxed_screening, run_screening
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


def _looks_garbled_name(name: str) -> bool:
    value = (name or "").strip()
    if not value:
        return True

    # Control chars or null bytes indicate broken decoding.
    if any((ord(ch) < 32 and ch not in ("\t", "\n", "\r")) for ch in value):
        return True

    has_hangul = any("\uac00" <= ch <= "\ud7a3" for ch in value)
    if has_hangul:
        return False

    # Common mojibake markers from broken cp949/utf-8 decoding.
    mojibake_markers = {"¤", "Ð", "À", "Ø", "Ü", "ð", "ñ", "õ", "ô", "ÿ"}
    if any(ch in mojibake_markers for ch in value):
        return True

    return False


def _parse_csv_tokens(raw: str) -> List[str]:
    return [token.strip() for token in (raw or "").split(",") if token.strip()]


def _normalize_csv_row_keys(row: Dict[str, str]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = key.strip().lstrip("\ufeffÿ")
        cleaned[normalized_key] = (value or "").strip()
    return cleaned


def _load_dart_universe(csv_path: str, allow_grades: Set[str]) -> Tuple[List[str], Dict[str, str]]:
    path = Path(csv_path)
    if not path.exists():
        return [], {}

    raw = path.read_bytes()
    if raw.startswith(b"\xff"):
        # Some generated CSVs prepend a lone 0xFF byte.
        raw = raw[1:]

    text = None
    for encoding in ("cp949", "euc-kr", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return [], {}

    reader = csv.DictReader(io.StringIO(text, newline=""))
    symbols: List[str] = []
    name_map: Dict[str, str] = {}
    seen: Set[str] = set()

    for raw_row in reader:
        row = _normalize_csv_row_keys(raw_row)
        grade = (row.get("grade") or "").upper()
        symbol = (row.get("stock_code") or "").strip()
        name = (row.get("name") or "").strip()
        if grade not in allow_grades:
            continue
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
        if name:
            name_map[symbol] = name

    return symbols, name_map


def _apply_composite_scores(
    results: List[Dict],
    store: MongoOHLCVStore,
    use_composite_score: bool,
    dart_weight: float,
    hiring_weight: float,
) -> List[Dict]:
    if not results:
        return results
    symbols = [str(row.get("symbol", "")).strip() for row in results if row.get("symbol")]
    dart_map = store.get_latest_dart_features(symbols) if store.enabled else {}
    hiring_map = store.get_latest_job_features(symbols) if store.enabled else {}

    grade_weight = {
        "TOP": 1.0,
        "STRONG": 0.75,
        "STRONG-": 0.6,
        "MID": 0.35,
        "WEAK": 0.1,
    }
    for row in results:
        symbol = str(row.get("symbol", "")).strip()
        tech_score = float(row.get("technical_score", 0.0))
        dart = dart_map.get(symbol, {})
        job = hiring_map.get(symbol, {})
        dart_grade = str(dart.get("grade", "")).upper()
        dart_score_raw = float(dart.get("score", 0.0))
        dart_component = max(grade_weight.get(dart_grade, 0.0), min(max(dart_score_raw, 0.0) / 100.0, 1.0))
        hiring_score = float(job.get("hiring_momentum_score", 0.0))
        hiring_component = min(max(hiring_score, 0.0) / 100.0, 1.0)

        composite = tech_score
        if use_composite_score:
            composite = tech_score + (dart_weight * dart_component) + (hiring_weight * hiring_component)

        row["dart_grade"] = dart_grade
        row["dart_score"] = round(dart_score_raw, 4)
        row["hiring_momentum_score"] = round(hiring_score, 4)
        row["hiring_posting_count_7d"] = int(job.get("posting_count_7d", 0))
        row["hiring_posting_count_30d"] = int(job.get("posting_count_30d", 0))
        row["composite_score"] = round(composite, 4)

    results.sort(key=lambda x: (float(x.get("composite_score", 0.0)), float(x.get("technical_score", 0.0))), reverse=True)
    return results


def _load_market_cap_map(client: KISClient, symbols: List[str]) -> Dict[str, int]:
    cache_path = Path(".cache/market_caps.json")
    cache_data: Dict[str, Dict] = {}
    if cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cache_data = loaded
        except json.JSONDecodeError:
            cache_data = {}

    out: Dict[str, int] = {}
    for symbol in symbols:
        cached = cache_data.get(symbol, {})
        cached_cap = int(cached.get("market_cap", 0)) if isinstance(cached, dict) else 0
        if cached_cap > 0:
            out[symbol] = cached_cap
            continue
        try:
            snap = client.get_price_snapshot(symbol)
            out[symbol] = int(snap.get("market_cap", 0))
        except Exception:
            out[symbol] = 0
    return out


def _fill_financials_if_missing(dataset: Dict[str, Dict], client: KISClient) -> None:
    for symbol, payload in dataset.items():
        financials = payload.get("financials", {})
        risk = set(financials.get("risk_flags", []))
        if "FUNDAMENTAL_DATA_MISSING" not in risk:
            continue
        try:
            payload["financials"] = client.get_financial_proxy(symbol)
        except Exception:
            continue


def _is_regular_market_session_now() -> bool:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.weekday() > 4:
        return False
    return dt_time(9, 0) <= now.time() <= dt_time(15, 30)


def run_once(args: argparse.Namespace) -> None:
    cfg = load_config()
    token_provider = KISTokenProvider(cfg)
    client = KISClient(cfg, token_provider, request_interval_seconds=args.request_interval)
    store = MongoOHLCVStore(cfg)
    print(f"[MONGO] enabled={store.enabled}")

    if args.migrate_dart_sqlite_path:
        migration_stat = migrate_dart_sqlite_to_mongo(
            store,
            sqlite_path=args.migrate_dart_sqlite_path,
            report_path=args.dart_report_path,
            batch_size=args.migrate_dart_batch_size,
        )
        print(
            "[DART_MIGRATION] "
            f"raw_rows={migration_stat['raw_rows']}, "
            f"raw_upserts={migration_stat['raw_upserts']}, "
            f"feature_upserts={migration_stat['feature_upserts']}"
        )

    symbol_name_map = _load_symbol_name_map()
    symbol_seed = args.symbols if args.symbols else _load_symbol_seed()
    dart_feature_seed_map: Dict[str, Dict] = {}
    if args.screen_mode == "dart-score" and not args.symbols and not args.use_dart_strong_universe:
        dart_feature_seed_map = store.list_latest_dart_features(min_score=args.dart_min_score if args.dart_min_score > 0 else None)
        symbol_seed = sorted(dart_feature_seed_map.keys())
        for symbol, feature in dart_feature_seed_map.items():
            corp_name = str(feature.get("corp_name", "")).strip()
            if corp_name and symbol not in symbol_name_map:
                symbol_name_map[symbol] = corp_name
        print(f"[DART_SCORE] symbols from dart features: {len(symbol_seed)}")
    if args.use_dart_strong_universe:
        allow_grades = {grade.upper() for grade in _parse_csv_tokens(args.dart_grades)}
        dart_symbols, dart_name_map = _load_dart_universe(args.dart_report_path, allow_grades)
        if not dart_symbols:
            print(f"[DART] no candidate symbols found in {args.dart_report_path}")
            return
        if args.symbols:
            dart_set = set(dart_symbols)
            symbol_seed = [symbol for symbol in args.symbols if symbol in dart_set]
        else:
            symbol_seed = dart_symbols
        for symbol, dart_name in dart_name_map.items():
            existing = (symbol_name_map.get(symbol) or "").strip()
            if existing and not _looks_garbled_name(existing):
                continue
            if _looks_garbled_name(dart_name):
                continue
            symbol_name_map[symbol] = dart_name
        print(
            f"[DART] source={args.dart_report_path}, grades={sorted(allow_grades)}, "
            f"selected_symbols={len(symbol_seed)}"
        )

    if not symbol_seed:
        print("No symbols found. Add data/symbols.txt or pass --symbols.")
        return

    has_explicit_seed = bool(args.symbols) or bool(args.use_dart_strong_universe)
    if args.data_source == "mongo":
        if has_explicit_seed:
            universe = list(symbol_seed)
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
        if args.collect_jobs:
            job_sources = [token.strip().lower() for token in _parse_csv_tokens(args.job_sources)]
            job_stats = collect_jobs_and_update_features(
                store,
                symbol_name_map=symbol_name_map,
                sources=job_sources,
                max_companies=args.job_max_companies,
                request_interval=args.job_request_interval,
            )
            print(
                "[JOBS] "
                f"requested={job_stats['requested']}, "
                f"posting_upserts={job_stats['posting_upserts']}, "
                f"feature_upserts={job_stats['feature_upserts']}"
            )
        print("[MODE] collect-only run completed.")
        return
    dataset, ref_date = _filter_dataset_by_recency(dataset, args.max_date_lag_days)
    print(f"[TIME] reference_date={ref_date}, max_date_lag_days={args.max_date_lag_days}, eligible={len(dataset)}")

    if args.screen_mode == "dart-score":
        if not dart_feature_seed_map:
            dart_feature_seed_map = store.get_latest_dart_features(list(dataset.keys())) if store.enabled else {}
        _fill_financials_if_missing(dataset, client)
        market_caps = _load_market_cap_map(client, list(dataset.keys()))
        results = run_dart_score_screening(
            dataset=dataset,
            dart_features=dart_feature_seed_map,
            market_caps=market_caps,
            min_market_cap_won=args.min_market_cap,
            target_count=args.target_count,
        )
        print(f"[DART_SCORE] result_count={len(results)}")
        for row in results:
            mapped_name = (symbol_name_map.get(row["symbol"]) or "").strip()
            row["name"] = mapped_name if mapped_name and not _looks_garbled_name(mapped_name) else row["symbol"]
    else:
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
            mapped_name = (symbol_name_map.get(row["symbol"]) or "").strip()
            row["name"] = mapped_name if mapped_name and not _looks_garbled_name(mapped_name) else row["symbol"]

        results = _apply_composite_scores(
            results,
            store=store,
            use_composite_score=args.use_composite_score,
            dart_weight=args.composite_dart_weight,
            hiring_weight=args.composite_hiring_weight,
        )
        if args.target_count > 0:
            results = results[: args.target_count]
    if args.collect_jobs:
        job_sources = [token.strip().lower() for token in _parse_csv_tokens(args.job_sources)]
        job_stats = collect_jobs_and_update_features(
            store,
            symbol_name_map=symbol_name_map,
            sources=job_sources,
            max_companies=args.job_max_companies,
            request_interval=args.job_request_interval,
        )
        print(
            "[JOBS] "
            f"requested={job_stats['requested']}, "
            f"posting_upserts={job_stats['posting_upserts']}, "
            f"feature_upserts={job_stats['feature_upserts']}"
        )

    print_console_table(results)
    report_path = save_csv(results)
    if report_path:
        print(f"CSV saved: {report_path}")
    else:
        print("No screening result: report file not created.")
    print_top5_summary(results)

    old_symbols = read_previous_symbols(args.state_path)
    newly_included = new_inclusions(results, old_symbols)
    can_send_telegram = True
    if args.telegram_market_hours_only and not _is_regular_market_session_now():
        can_send_telegram = False

    if args.skip_telegram:
        print("[TELEGRAM] skipped by --skip-telegram")
    elif not can_send_telegram:
        print("[TELEGRAM] skipped (outside regular market session)")
    elif args.telegram_mode == "full":
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
            if args.notify_when_empty:
                send_telegram(
                    cfg.telegram_bot_token,
                    cfg.telegram_chat_id,
                    args.empty_notify_message or "[KIS Screener] 현재 신규 없음",
                )
                print("Telegram notified: no new inclusion.")
            print("No new inclusion vs previous run.")

    save_current_symbols(set(row["symbol"] for row in results), args.state_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KIS domestic stock screener")
    parser.add_argument("--screen-mode", choices=["pattern", "dart-score"], default="pattern")
    parser.add_argument("--symbols", nargs="*", help="Explicit symbol list for debug or focused run")
    parser.add_argument(
        "--use-dart-strong-universe",
        action="store_true",
        help="Use symbols in dart/report.csv filtered by grades (default: TOP,STRONG,STRONG-)",
    )
    parser.add_argument("--dart-report-path", default="dart/report.csv")
    parser.add_argument("--dart-grades", default="TOP,STRONG,STRONG-")
    parser.add_argument("--dart-min-score", type=float, default=0.0)
    parser.add_argument("--migrate-dart-sqlite-path", default="")
    parser.add_argument("--migrate-dart-batch-size", type=int, default=500)
    parser.add_argument("--collect-jobs", action="store_true", help="Collect hiring postings and refresh hiring features")
    parser.add_argument("--job-sources", default="saramin,jobkorea")
    parser.add_argument("--job-max-companies", type=int, default=120)
    parser.add_argument("--job-request-interval", type=float, default=0.4)
    parser.add_argument("--use-composite-score", action="store_true")
    parser.add_argument("--composite-dart-weight", type=float, default=1.2)
    parser.add_argument("--composite-hiring-weight", type=float, default=1.0)
    parser.add_argument("--data-source", choices=["live", "mongo"], default="live")
    parser.add_argument("--mongo-ohlcv-limit", type=int, default=500)
    parser.add_argument("--use-universe-file", action="store_true", help="Use data/universe_100b.txt in mongo mode")
    parser.add_argument("--collect-only", action="store_true", help="Only collect/update data without screening outputs")
    parser.add_argument("--skip-telegram", action="store_true", help="Skip Telegram notification during this run")
    parser.add_argument("--telegram-mode", choices=["new", "full"], default="new")
    parser.add_argument("--telegram-title", default="")
    parser.add_argument(
        "--telegram-market-hours-only",
        action="store_true",
        help="Send telegram only during regular market hours (KST 09:00-15:30, weekdays)",
    )
    parser.add_argument("--notify-when-empty", action="store_true", help="Notify telegram even when no new inclusion")
    parser.add_argument("--empty-notify-message", default="[KIS Screener] 현재 신규 없음")
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
    parser.add_argument("--target-count", type=int, default=7, help="Target number of screening results")
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
    parser.add_argument(
        "--realtime-sync-loop",
        action="store_true",
        help="Continuously poll inquire-price and merge into MongoDB daily_ohlcv (today's bar).",
    )
    parser.add_argument(
        "--realtime-regular-only",
        action="store_true",
        help="Realtime sync only during KST 09:00-15:30 (default: 08:00-20:00 NXT-style window).",
    )
    parser.add_argument("--realtime-universe-file", default="data/universe_100b.txt")
    parser.add_argument("--realtime-cycle-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.realtime_sync_loop:
        from .realtime_sync import run_realtime_sync_loop

        run_realtime_sync_loop(args)
        return
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

