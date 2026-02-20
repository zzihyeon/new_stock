from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .kis_client import KISClient
from .storage import MongoOHLCVStore, merge_ohlcv_rows


def chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def load_symbols_from_file(file_path: str = "data/symbols.txt") -> List[str]:
    path = Path(file_path)
    if not path.exists():
        # Graceful fallback: a small default universe
        return ["005930", "000660", "035420", "035720", "051910", "068270"]

    symbols: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            symbols.append(line)
    return sorted(set(symbols))


def load_symbols_from_csv(csv_path: str = "data/symbols.csv", column: str = "symbol") -> List[str]:
    path = Path(csv_path)
    if not path.exists():
        return []
    symbols: List[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            value = row.get(column, "").strip()
            if value:
                symbols.append(value)
    return sorted(set(symbols))


def build_universe_by_market_cap(
    client: KISClient,
    symbols: List[str],
    min_market_cap_won: int = 100_000_000_000,
    batch_size: int = 40,
    cache_path: str = ".cache/market_caps.json",
    cache_ttl_seconds: int = 24 * 60 * 60,
) -> List[str]:
    """
    Universe condition:
      - market cap >= 100 billion KRW
    """
    universe: List[str] = []
    market_cap_cache, cache_dirty = _load_market_cap_cache(cache_path), False
    now = time.time()

    for batch in chunked(symbols, batch_size):
        for symbol in batch:
            try:
                cached = market_cap_cache.get(symbol)
                if cached and now - float(cached.get("updated_at", 0)) <= cache_ttl_seconds:
                    market_cap = int(cached.get("market_cap", 0))
                else:
                    snapshot = client.get_price_snapshot(symbol)
                    market_cap = int(snapshot.get("market_cap", 0))
                    market_cap_cache[symbol] = {"market_cap": market_cap, "updated_at": now}
                    cache_dirty = True

                if market_cap >= min_market_cap_won:
                    universe.append(symbol)
            except Exception:
                # fallback gracefully on missing/error data
                continue
    if cache_dirty:
        _save_market_cap_cache(cache_path, market_cap_cache)
    return universe


def collect_market_dataset(
    client: KISClient,
    universe: List[str],
    batch_size: int = 30,
    store: MongoOHLCVStore | None = None,
) -> Dict[str, dict]:
    dataset: Dict[str, dict] = {}
    for batch in chunked(universe, batch_size):
        for symbol in batch:
            ohlcv: List[dict] = []
            financials: dict = {"risk_flags": []}

            try:
                ohlcv = client.get_daily_ohlcv(symbol)
                if not ohlcv:
                    time.sleep(0.25)
                    ohlcv = client.get_daily_ohlcv(symbol)
            except Exception as exc:
                financials["risk_flags"] = [f"OHLCV_ERROR:{exc}"]

            if store is not None and ohlcv:
                try:
                    store.upsert_ohlcv(symbol, ohlcv)
                except Exception as exc:
                    risk_flags = list(financials.get("risk_flags", []))
                    risk_flags.append(f"MONGO_WRITE_ERROR:{exc}")
                    financials["risk_flags"] = risk_flags

            if store is not None:
                try:
                    db_rows = store.load_ohlcv(symbol, limit=500)
                    ohlcv = merge_ohlcv_rows(db_rows, ohlcv, limit=500)
                except Exception as exc:
                    risk_flags = list(financials.get("risk_flags", []))
                    risk_flags.append(f"MONGO_READ_ERROR:{exc}")
                    financials["risk_flags"] = risk_flags

            try:
                financials = client.get_financial_proxy(symbol)
            except Exception as exc:
                risk_flags = list(financials.get("risk_flags", []))
                risk_flags.append(f"FUNDAMENTAL_ERROR:{exc}")
                financials["risk_flags"] = risk_flags

            dataset[symbol] = {"ohlcv": ohlcv, "financials": financials}
    return dataset


def collect_market_dataset_from_store(store: MongoOHLCVStore, symbols: List[str], limit: int = 500) -> Dict[str, dict]:
    dataset: Dict[str, dict] = {}
    for symbol in symbols:
        rows = store.load_ohlcv(symbol, limit=limit) if store.enabled else []
        dataset[symbol] = {
            "ohlcv": rows,
            # Stored data mode keeps analysis running even when fundamentals are unavailable.
            "financials": {"risk_flags": ["FUNDAMENTAL_DATA_MISSING"]},
        }
    return dataset


def _load_market_cap_cache(path: str) -> Dict[str, dict]:
    cache_file = Path(path)
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return {}
    return {}


def _save_market_cap_cache(path: str, data: Dict[str, dict]) -> None:
    cache_file = Path(path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")

