from __future__ import annotations

from typing import Dict, List, Optional

from pymongo import ASCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from .auth import KISConfig


class MongoOHLCVStore:
    def __init__(self, config: KISConfig) -> None:
        self._enabled = bool(config.mongodb_uri)
        self._collection: Optional[Collection] = None

        if not self._enabled:
            return

        try:
            client = MongoClient(config.mongodb_uri, serverSelectionTimeoutMS=5000)
            db = client[config.mongodb_db_name]
            self._collection = db["daily_ohlcv"]
            self._collection.create_index([("symbol", ASCENDING), ("date", ASCENDING)], unique=True)
            self._collection.create_index([("symbol", ASCENDING), ("date", -1)])
        except PyMongoError:
            self._collection = None

    @property
    def enabled(self) -> bool:
        return self._collection is not None

    def upsert_ohlcv(self, symbol: str, rows: List[Dict]) -> None:
        if not self.enabled or not rows:
            return
        ops: List[UpdateOne] = []
        for row in rows:
            if not row.get("date"):
                continue
            doc = {
                "symbol": symbol,
                "date": row["date"],
                "open": int(row.get("open", 0)),
                "high": int(row.get("high", 0)),
                "low": int(row.get("low", 0)),
                "close": int(row.get("close", 0)),
                "volume": int(row.get("volume", 0)),
                "trading_value": int(row.get("trading_value", 0)),
            }
            ops.append(
                UpdateOne(
                    {"symbol": symbol, "date": row["date"]},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if ops:
            self._collection.bulk_write(ops, ordered=False)  # type: ignore[union-attr]

    def load_ohlcv(self, symbol: str, limit: int = 400) -> List[Dict]:
        if not self.enabled:
            return []
        cursor = (
            self._collection.find({"symbol": symbol}, {"_id": 0})  # type: ignore[union-attr]
            .sort("date", ASCENDING)
            .limit(max(limit, 1))
        )
        return list(cursor)

    def list_symbols(self) -> List[str]:
        if not self.enabled:
            return []
        symbols = self._collection.distinct("symbol")  # type: ignore[union-attr]
        return sorted(str(s) for s in symbols if s)


def merge_ohlcv_rows(db_rows: List[Dict], api_rows: List[Dict], limit: int = 400) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for row in db_rows:
        d = str(row.get("date", ""))
        if d:
            merged[d] = row
    for row in api_rows:
        d = str(row.get("date", ""))
        if d:
            merged[d] = row
    rows = [merged[key] for key in sorted(merged.keys())]
    if len(rows) > limit:
        rows = rows[-limit:]
    return rows

