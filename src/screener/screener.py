from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .indicators import compute_core_indicators, detect_d0_surge_indices, is_bullish_candle, support_check


@dataclass
class ScreenConfig:
    min_market_cap_won: int = 100_000_000_000
    d0_vol_multiple: float = 1.2
    d1_volume_drop_ratio: float = 0.3  # >=30% drop
    min_current_volume: int = 1_000_000
    min_recent_n_volume: int = 1_000_000
    recent_volume_lookback_days: int = 5
    d0_tv_percentile_min: float = 45.0
    d0_surge_require_both: bool = False
    pattern_a_pullback_days: int = 6
    allow_b_days_after_d0: int = 3
    max_one_day_rise_pct: float = 8.0
    max_three_day_rise_pct: float = 15.0
    min_pullback_from_recent_high_pct: float = 1.0
    max_pullback_from_recent_high_pct: float = 18.0
    max_candidates: int = 50


def financial_improvement_pass(financials: Dict) -> bool:
    """
    Improvement rule: pass if at least 2 of 3 are satisfied.
      1) operating income improvement
      2) sales + margin improvement
      3) OCF improvement
    """
    op_income = float(financials.get("op_income_growth", 0.0))
    sales = float(financials.get("sales_growth", 0.0))
    margin = float(financials.get("margin_change", 0.0))
    ocf = float(financials.get("ocf_growth", 0.0))

    risk_flags = set(financials.get("risk_flags", []))
    if "FUNDAMENTAL_DATA_MISSING" in risk_flags:
        return True

    checks = [
        op_income > 0,
        sales > 0 and margin > 0,
        ocf > 0,
    ]
    return sum(1 for x in checks if x) >= 2


def _volume_drop_ratio(base_volume: float, next_volume: float) -> float:
    if base_volume <= 0:
        return 0.0
    return (base_volume - next_volume) / base_volume


def _pct_change(new_value: float, old_value: float) -> float:
    if old_value <= 0:
        return 0.0
    return ((new_value - old_value) / old_value) * 100.0


def _is_overheated_or_not_pullback(ohlcv: List[Dict], cfg: ScreenConfig) -> bool:
    if len(ohlcv) < 5:
        return True

    latest = float(ohlcv[-1]["close"])
    prev1 = float(ohlcv[-2]["close"])
    prev3 = float(ohlcv[-4]["close"]) if len(ohlcv) >= 4 else prev1

    one_day_rise = _pct_change(latest, prev1)
    three_day_rise = _pct_change(latest, prev3)
    if one_day_rise > cfg.max_one_day_rise_pct or three_day_rise > cfg.max_three_day_rise_pct:
        return True

    window = ohlcv[-20:] if len(ohlcv) >= 20 else ohlcv
    recent_high = max(float(x["high"]) for x in window)
    if recent_high <= 0:
        return True

    pullback_pct = ((recent_high - latest) / recent_high) * 100.0
    if pullback_pct < cfg.min_pullback_from_recent_high_pct:
        return True
    if pullback_pct > cfg.max_pullback_from_recent_high_pct:
        return True
    return False


def _passes_recent_volume_filter(ohlcv: List[Dict], cfg: ScreenConfig) -> bool:
    if not ohlcv:
        return False
    lookback = max(cfg.recent_volume_lookback_days, 1)
    window = ohlcv[-lookback:] if len(ohlcv) >= lookback else ohlcv
    recent_max_volume = max(int(x.get("volume", 0)) for x in window)
    return recent_max_volume >= cfg.min_recent_n_volume


def evaluate_pattern_a(ohlcv: List[Dict], indicators: Dict, cfg: ScreenConfig) -> Optional[Dict]:
    """
    Pattern A (양음양):
      D0 big bullish + D1 volume sharp drop + support hold.
    """
    d0_indices = detect_d0_surge_indices(
        ohlcv,
        indicators,
        vol_multiple=cfg.d0_vol_multiple,
        tv_percentile_min=cfg.d0_tv_percentile_min,
        require_both=cfg.d0_surge_require_both,
    )
    if not d0_indices:
        return None

    for d0_idx in d0_indices:
        d0 = ohlcv[d0_idx]
        for offset in range(1, cfg.pattern_a_pullback_days + 1):
            idx = d0_idx + offset
            if idx >= len(ohlcv):
                break
            d1 = ohlcv[idx]
            drop = _volume_drop_ratio(d0["volume"], d1["volume"])
            if drop < cfg.d1_volume_drop_ratio:
                continue

            supported, support_reasons = support_check(ohlcv, indicators, d0_idx, idx)
            if not supported:
                continue

            return {
                "pattern": "NUGUL_STOCK_POINT",
                "d0_date": d0["date"],
                "d1_date": d1["date"],
                "confirm_offset": offset,
                "d0_volume": d0["volume"],
                "d1_volume": d1["volume"],
                "d1_drop_ratio": round(drop, 4),
                "support_reasons": support_reasons,
            }
    return None


def evaluate_pattern_b(ohlcv: List[Dict], indicators: Dict, cfg: ScreenConfig) -> Optional[Dict]:
    """
    Pattern B (200MA below):
      D0 happens below MA200, then D1~D3 volume contracts and support holds.
    """
    d0_indices = detect_d0_surge_indices(
        ohlcv,
        indicators,
        vol_multiple=cfg.d0_vol_multiple,
        tv_percentile_min=cfg.d0_tv_percentile_min,
        require_both=cfg.d0_surge_require_both,
    )
    if not d0_indices:
        return None

    for d0_idx in d0_indices:
        ma200 = indicators["ma200"][d0_idx]
        if ma200 != ma200:  # NaN check
            continue
        if ohlcv[d0_idx]["close"] >= ma200:
            continue

        d0 = ohlcv[d0_idx]
        for offset in range(1, cfg.allow_b_days_after_d0 + 1):
            idx = d0_idx + offset
            if idx >= len(ohlcv):
                break
            drop = _volume_drop_ratio(d0["volume"], ohlcv[idx]["volume"])
            if drop < cfg.d1_volume_drop_ratio:
                continue
            supported, support_reasons = support_check(ohlcv, indicators, d0_idx, idx)
            if not supported:
                continue
            return {
                "pattern": "B_BELOW_200MA",
                "d0_date": d0["date"],
                "confirm_date": ohlcv[idx]["date"],
                "confirm_offset": offset,
                "d0_volume": d0["volume"],
                "confirm_volume": ohlcv[idx]["volume"],
                "drop_ratio": round(drop, 4),
                "support_reasons": support_reasons,
            }
    return None


def run_screening(dataset: Dict[str, Dict], cfg: ScreenConfig, debug_symbols: Optional[List[str]] = None) -> List[Dict]:
    results: List[Dict] = []
    debug_set = set(debug_symbols or [])

    for symbol, payload in dataset.items():
        ohlcv = payload.get("ohlcv", [])
        financials = payload.get("financials", {})
        risk_flags = list(financials.get("risk_flags", []))

        # Some broker endpoints return 30~120 bars depending on account/product.
        # Keep screening active with available history instead of dropping everything.
        if len(ohlcv) < 30:
            if symbol in debug_set:
                print(f"[DEBUG:{symbol}] skipped: insufficient ohlcv={len(ohlcv)}")
            continue

        latest = ohlcv[-1]
        if latest.get("volume", 0) < cfg.min_current_volume:
            if symbol in debug_set:
                print(
                    f"[DEBUG:{symbol}] skipped: latest_volume={latest.get('volume', 0)} < {cfg.min_current_volume}"
                )
            continue
        if not _passes_recent_volume_filter(ohlcv, cfg):
            if symbol in debug_set:
                print(
                    f"[DEBUG:{symbol}] skipped: recent {cfg.recent_volume_lookback_days}d max volume < {cfg.min_recent_n_volume}"
                )
            continue
        if _is_overheated_or_not_pullback(ohlcv, cfg):
            if symbol in debug_set:
                print(f"[DEBUG:{symbol}] skipped: overheated or not in pullback zone")
            continue

        indicators = compute_core_indicators(ohlcv)
        a_hit = evaluate_pattern_a(ohlcv, indicators, cfg)
        b_hit = evaluate_pattern_b(ohlcv, indicators, cfg)
        fin_ok = financial_improvement_pass(financials)

        if symbol in debug_set:
            print(f"[DEBUG:{symbol}] patternA={bool(a_hit)} patternB={bool(b_hit)} fin={fin_ok} risk={risk_flags}")

        if not (a_hit or b_hit):
            continue

        if not fin_ok:
            continue

        result = {
            "symbol": symbol,
            "close": latest["close"],
            "latest_date": latest["date"],
            "latest_volume": latest.get("volume", 0),
            "pattern": (a_hit or b_hit)["pattern"],
            "details": a_hit or b_hit,
            "risk_flags": risk_flags,
            "manual_review": len(risk_flags) > 0,
        }
        results.append(result)

    return results[: cfg.max_candidates]


def run_relaxed_screening(
    dataset: Dict[str, Dict],
    cfg: ScreenConfig,
    target_count: int,
    exclude_symbols: Optional[set[str]] = None,
) -> List[Dict]:
    """
    Relaxed fallback screening:
    - keeps min current volume constraint
    - allows weaker D0 surge/pullback
    - used only when strict screening results are insufficient
    """
    exclude_symbols = exclude_symbols or set()
    candidates: List[Dict] = []

    for symbol, payload in dataset.items():
        if symbol in exclude_symbols:
            continue

        ohlcv = payload.get("ohlcv", [])
        financials = payload.get("financials", {})
        risk_flags = list(financials.get("risk_flags", []))
        if len(ohlcv) < 30:
            continue

        latest = ohlcv[-1]
        if latest.get("volume", 0) < cfg.min_current_volume:
            continue
        if not _passes_recent_volume_filter(ohlcv, cfg):
            continue
        if _is_overheated_or_not_pullback(ohlcv, cfg):
            continue

        indicators = compute_core_indicators(ohlcv)
        d0_indices = detect_d0_surge_indices(
            ohlcv,
            indicators,
            vol_multiple=max(cfg.d0_vol_multiple * 0.65, 0.5),
            tv_percentile_min=max(cfg.d0_tv_percentile_min * 0.6, 0.0),
            require_both=False,
        )
        if not d0_indices:
            continue

        picked = None
        for d0_idx in d0_indices:
            d0 = ohlcv[d0_idx]
            if not is_bullish_candle(d0):
                continue

            max_offset = max(cfg.pattern_a_pullback_days + 2, 8)
            for offset in range(1, max_offset + 1):
                idx = d0_idx + offset
                if idx >= len(ohlcv):
                    break
                pullback = ohlcv[idx]
                drop = _volume_drop_ratio(d0["volume"], pullback["volume"])
                supported, support_reasons = support_check(ohlcv, indicators, d0_idx, idx)
                if not supported:
                    continue
                if drop < max(cfg.d1_volume_drop_ratio - 0.35, -0.3):
                    continue

                score = (
                    len(support_reasons) * 1.5
                    + max(drop, 0.0) * 3.0
                    + (min(d0["volume"], 50_000_000) / 50_000_000)
                )
                picked = {
                    "symbol": symbol,
                    "close": latest["close"],
                    "latest_date": latest["date"],
                    "latest_volume": latest.get("volume", 0),
                    "pattern": "A_RELAXED",
                    "details": {
                        "pattern": "A_RELAXED",
                        "d0_date": d0["date"],
                        "d1_date": pullback["date"],
                        "confirm_offset": offset,
                        "d0_volume": d0["volume"],
                        "d1_volume": pullback["volume"],
                        "d1_drop_ratio": round(drop, 4),
                        "support_reasons": support_reasons,
                        "score": round(score, 4),
                    },
                    "risk_flags": risk_flags,
                    "manual_review": True,
                }
                break
            if picked:
                break

        if picked:
            candidates.append(picked)

    candidates.sort(key=lambda x: float(x["details"].get("score", 0.0)), reverse=True)
    need = max(target_count, 0)
    return candidates[:need]

