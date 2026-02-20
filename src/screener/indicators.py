from __future__ import annotations

import math
from typing import Dict, List, Tuple


def moving_average(values: List[float], period: int) -> List[float]:
    if period <= 0:
        raise ValueError("period must be positive")
    out = [math.nan] * len(values)
    rolling_sum = 0.0
    for i, value in enumerate(values):
        rolling_sum += value
        if i >= period:
            rolling_sum -= values[i - period]
        if i >= period - 1:
            out[i] = rolling_sum / period
    return out


def percentile_rank(value: float, values: List[float]) -> float:
    if not values:
        return 0.0
    less_or_equal = sum(1 for v in values if v <= value)
    return (less_or_equal / len(values)) * 100.0


def compute_core_indicators(ohlcv: List[Dict]) -> Dict:
    closes = [float(row["close"]) for row in ohlcv]
    volumes = [float(row["volume"]) for row in ohlcv]
    trading_values = [float(row["trading_value"]) for row in ohlcv]

    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    ma200 = moving_average(closes, 200)

    avg_vol20 = moving_average(volumes, 20)
    tv60 = trading_values[-60:] if len(trading_values) >= 60 else trading_values
    tv_percentile60 = [
        percentile_rank(v, tv60 if len(tv60) > 0 else [1.0]) for v in trading_values
    ]

    return {
        "close": closes,
        "volume": volumes,
        "trading_value": trading_values,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "ma200": ma200,
        "avg_vol20": avg_vol20,
        "tv_percentile60": tv_percentile60,
    }


def is_bullish_candle(row: Dict) -> bool:
    return row["close"] > row["open"]


def body_mid_price(row: Dict) -> float:
    return (row["open"] + row["close"]) / 2.0


def detect_d0_surge(
    ohlcv: List[Dict],
    indicators: Dict,
    vol_multiple: float = 1.6,
    lookback_days: int = 20,
    tv_percentile_min: float = 70.0,
    require_both: bool = False,
) -> int:
    indices = detect_d0_surge_indices(
        ohlcv,
        indicators,
        vol_multiple=vol_multiple,
        lookback_days=lookback_days,
        tv_percentile_min=tv_percentile_min,
        require_both=require_both,
    )
    return indices[0] if indices else -1


def detect_d0_surge_indices(
    ohlcv: List[Dict],
    indicators: Dict,
    vol_multiple: float = 1.6,
    lookback_days: int = 20,
    tv_percentile_min: float = 70.0,
    require_both: bool = False,
) -> List[int]:
    """
    Return all recent D0 candidate indices, newest first.
    D0 must be bullish and volume/trading value surge.
    """
    if len(ohlcv) < 25:
        return []
    start = max(20, len(ohlcv) - lookback_days)
    out: List[int] = []
    for idx in range(len(ohlcv) - 1, start - 1, -1):
        row = ohlcv[idx]
        if not is_bullish_candle(row):
            continue
        avg20 = indicators["avg_vol20"][idx]
        if math.isnan(avg20) or avg20 <= 0:
            continue
        vol_surge = row["volume"] >= avg20 * vol_multiple
        tv_pct = indicators["tv_percentile60"][idx]
        tv_surge = tv_pct >= tv_percentile_min
        is_surge = (vol_surge and tv_surge) if require_both else (vol_surge or tv_surge)
        if is_surge:
            out.append(idx)
    return out


def support_check(
    ohlcv: List[Dict], indicators: Dict, d0_idx: int, current_idx: int
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    current = ohlcv[current_idx]
    d0 = ohlcv[d0_idx]

    ma20 = indicators["ma20"][current_idx]
    if not math.isnan(ma20) and current["close"] >= ma20:
        reasons.append("SUPPORT_MA20")

    if current["close"] >= d0["low"]:
        reasons.append("SUPPORT_D0_LOW")

    if current["close"] >= body_mid_price(d0):
        reasons.append("SUPPORT_D0_BODY50")

    if current_idx > 0 and current["close"] >= ohlcv[current_idx - 1]["low"]:
        reasons.append("SUPPORT_PREV_LOW")

    return (len(reasons) > 0, reasons)

