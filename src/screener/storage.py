from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from .auth import KISConfig


class MongoOHLCVStore:
    def __init__(self, config: KISConfig) -> None:
        self._enabled = bool(config.mongodb_uri)
        self._collection: Optional[Collection] = None
        self._dart_emp_raw: Optional[Collection] = None
        self._dart_emp_features: Optional[Collection] = None
        self._job_postings: Optional[Collection] = None
        self._job_features: Optional[Collection] = None

        if not self._enabled:
            return

        try:
            client = MongoClient(config.mongodb_uri, serverSelectionTimeoutMS=5000)
            db = client[config.mongodb_db_name]
            self._collection = db["daily_ohlcv"]
            self._dart_emp_raw = db["dart_emp_raw"]
            self._dart_emp_features = db["dart_emp_features"]
            self._job_postings = db["job_postings"]
            self._job_features = db["job_features"]

            self._collection.create_index([("symbol", ASCENDING), ("date", ASCENDING)], unique=True)
            self._collection.create_index([("symbol", ASCENDING), ("date", -1)])
            self._dart_emp_raw.create_index(
                [("corp_code", ASCENDING), ("bsns_year", ASCENDING), ("reprt_code", ASCENDING)],
                unique=True,
            )
            self._dart_emp_raw.create_index([("stock_code", ASCENDING)])
            self._dart_emp_features.create_index(
                [("corp_code", ASCENDING), ("as_of_period", ASCENDING)],
                unique=True,
            )
            self._dart_emp_features.create_index([("stock_code", ASCENDING), ("computed_at", -1)])
            self._job_postings.create_index([("source", ASCENDING), ("external_id", ASCENDING)], unique=True)
            self._job_postings.create_index([("symbol", ASCENDING), ("posted_at", DESCENDING)])
            self._job_postings.create_index([("collected_at", DESCENDING)])
            self._job_features.create_index([("symbol", ASCENDING), ("as_of_date", ASCENDING)], unique=True)
            self._job_features.create_index([("computed_at", DESCENDING)])
        except PyMongoError:
            self._collection = None
            self._dart_emp_raw = None
            self._dart_emp_features = None
            self._job_postings = None
            self._job_features = None

    @property
    def enabled(self) -> bool:
        return (
            self._collection is not None
            and self._dart_emp_raw is not None
            and self._dart_emp_features is not None
            and self._job_postings is not None
            and self._job_features is not None
        )

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

    def upsert_today_from_snapshot(self, symbol: str, trading_date: str, snap: Dict) -> None:
        """
        Merge inquire-price snapshot into daily_ohlcv for trading_date (YYYYMMDD).
        Used by realtime sync so screening can read MongoDB with an up-to-date last bar.
        """
        if not self._collection or not trading_date:
            return
        close_p = int(snap.get("close", 0) or 0)
        open_p = int(snap.get("open", 0) or 0)
        high_p = int(snap.get("high", 0) or 0)
        low_p = int(snap.get("low", 0) or 0)
        vol = int(snap.get("volume", 0) or 0)
        tv = int(snap.get("trading_value", 0) or 0)

        existing = self._collection.find_one({"symbol": symbol, "date": trading_date}, {"_id": 0})  # type: ignore[union-attr]
        if not existing:
            o = open_p or close_p
            c = close_p or o
            h = max(high_p or c, c, o)
            candidates_l = [x for x in (low_p, c, o) if x and x > 0]
            l = min(candidates_l) if candidates_l else (low_p or c or o)
            if tv <= 0 and c > 0 and vol > 0:
                tv = c * vol
            doc = {
                "symbol": symbol,
                "date": trading_date,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": vol,
                "trading_value": tv,
            }
            self._collection.update_one({"symbol": symbol, "date": trading_date}, {"$set": doc}, upsert=True)  # type: ignore[union-attr]
            return

        eo = int(existing.get("open", 0) or 0)
        eh = int(existing.get("high", 0) or 0)
        el = int(existing.get("low", 0) or 0)
        ec = int(existing.get("close", 0) or 0)
        ev = int(existing.get("volume", 0) or 0)

        o = eo or open_p or close_p
        c = close_p or ec
        h = max(eh, high_p or 0, c, o)
        candidates_l = [x for x in (el, low_p, c, o) if x and x > 0]
        if candidates_l:
            l = min(candidates_l)
        else:
            l = low_p or c or o or el or 0
        v = max(vol, ev)
        merged_tv = int(existing.get("trading_value", 0) or 0)
        if tv > merged_tv:
            merged_tv = tv
        if merged_tv <= 0 and c > 0 and v > 0:
            merged_tv = c * v

        doc = {
            "symbol": symbol,
            "date": trading_date,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "trading_value": merged_tv,
        }
        self._collection.update_one({"symbol": symbol, "date": trading_date}, {"$set": doc}, upsert=True)  # type: ignore[union-attr]

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

    def upsert_dart_raw(self, records: List[Dict]) -> int:
        if not self.enabled or not records:
            return 0
        ops: List[UpdateOne] = []
        for row in records:
            corp_code = str(row.get("corp_code", "")).strip()
            bsns_year = int(row.get("bsns_year", 0))
            reprt_code = str(row.get("reprt_code", "")).strip()
            if not corp_code or not bsns_year or not reprt_code:
                continue
            doc = {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "stock_code": str(row.get("stock_code", "")).strip(),
                "corp_name": str(row.get("corp_name", "")).strip(),
                "payload": row.get("payload"),
                "status": str(row.get("status", "")).strip(),
                "updated_at": int(row.get("updated_at", 0)),
                "source": "sqlite_emp_cache",
                "migrated_at": datetime.utcnow(),
            }
            ops.append(
                UpdateOne(
                    {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if not ops:
            return 0
        result = self._dart_emp_raw.bulk_write(ops, ordered=False)  # type: ignore[union-attr]
        return int(result.upserted_count + result.modified_count)

    def upsert_dart_features(self, rows: List[Dict]) -> int:
        if not self.enabled or not rows:
            return 0
        ops: List[UpdateOne] = []
        now = datetime.utcnow()
        for row in rows:
            corp_code = str(row.get("corp_code", "")).strip()
            as_of_period = str(row.get("as_of_period", "")).strip()
            if not corp_code or not as_of_period:
                continue
            doc = {**row, "computed_at": row.get("computed_at") or now}
            ops.append(
                UpdateOne(
                    {"corp_code": corp_code, "as_of_period": as_of_period},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if not ops:
            return 0
        result = self._dart_emp_features.bulk_write(ops, ordered=False)  # type: ignore[union-attr]
        return int(result.upserted_count + result.modified_count)

    def get_latest_dart_features(self, symbols: List[str]) -> Dict[str, Dict]:
        if not self.enabled or not symbols:
            return {}
        symbol_set = sorted({s for s in symbols if s})
        if not symbol_set:
            return {}
        pipeline = [
            {"$match": {"stock_code": {"$in": symbol_set}}},
            {"$sort": {"computed_at": -1}},
            {"$group": {"_id": "$stock_code", "doc": {"$first": "$$ROOT"}}},
        ]
        rows = list(self._dart_emp_features.aggregate(pipeline))  # type: ignore[union-attr]
        out: Dict[str, Dict] = {}
        for row in rows:
            symbol = str(row.get("_id", "")).strip()
            doc = row.get("doc", {})
            if symbol and isinstance(doc, dict):
                out[symbol] = doc
        return out

    def list_latest_dart_features(self, min_score: Optional[float] = None) -> Dict[str, Dict]:
        if not self.enabled:
            return {}
        pipeline: List[Dict] = [
            {"$match": {"stock_code": {"$exists": True, "$ne": ""}}},
            {"$sort": {"computed_at": -1}},
            {"$group": {"_id": "$stock_code", "doc": {"$first": "$$ROOT"}}},
        ]
        if min_score is not None:
            pipeline.append({"$match": {"doc.score": {"$gte": float(min_score)}}})
        rows = list(self._dart_emp_features.aggregate(pipeline))  # type: ignore[union-attr]
        out: Dict[str, Dict] = {}
        for row in rows:
            symbol = str(row.get("_id", "")).strip()
            doc = row.get("doc", {})
            if symbol and isinstance(doc, dict):
                out[symbol] = doc
        return out

    def upsert_job_postings(self, postings: List[Dict]) -> int:
        if not self.enabled or not postings:
            return 0
        now = datetime.utcnow()
        ops: List[UpdateOne] = []
        for row in postings:
            source = str(row.get("source", "")).strip()
            external_id = str(row.get("external_id", "")).strip()
            if not source or not external_id:
                continue
            doc = {
                **row,
                "source": source,
                "external_id": external_id,
                "collected_at": row.get("collected_at") or now,
            }
            ops.append(
                UpdateOne(
                    {"source": source, "external_id": external_id},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if not ops:
            return 0
        result = self._job_postings.bulk_write(ops, ordered=False)  # type: ignore[union-attr]
        return int(result.upserted_count + result.modified_count)

    def recompute_job_features(self, as_of_date: Optional[str] = None) -> int:
        if not self.enabled:
            return 0
        if as_of_date:
            try:
                as_of_dt = datetime.strptime(as_of_date, "%Y%m%d")
            except ValueError:
                as_of_dt = datetime.utcnow()
        else:
            as_of_dt = datetime.utcnow()
        d7 = as_of_dt - timedelta(days=7)
        d30 = as_of_dt - timedelta(days=30)
        d14_prev = as_of_dt - timedelta(days=14)
        d7_prev = as_of_dt - timedelta(days=7)

        symbols = [str(s) for s in self._job_postings.distinct("symbol") if s]  # type: ignore[union-attr]
        ops: List[UpdateOne] = []
        for symbol in symbols:
            count_7d = self._job_postings.count_documents(  # type: ignore[union-attr]
                {"symbol": symbol, "posted_at_dt": {"$gte": d7, "$lte": as_of_dt}}
            )
            count_30d = self._job_postings.count_documents(  # type: ignore[union-attr]
                {"symbol": symbol, "posted_at_dt": {"$gte": d30, "$lte": as_of_dt}}
            )
            prev_7d = self._job_postings.count_documents(  # type: ignore[union-attr]
                {"symbol": symbol, "posted_at_dt": {"$gte": d14_prev, "$lt": d7_prev}}
            )
            delta = count_7d - prev_7d
            base = max(prev_7d, 1)
            growth_rate = (delta / base) * 100.0
            momentum = round(min(100.0, max(0.0, (count_7d * 8.0) + growth_rate)), 3)
            matched_sources = self._job_postings.distinct("source", {"symbol": symbol})  # type: ignore[union-attr]
            doc = {
                "symbol": symbol,
                "as_of_date": as_of_dt.strftime("%Y%m%d"),
                "posting_count_7d": int(count_7d),
                "posting_count_30d": int(count_30d),
                "new_posting_delta": int(delta),
                "hiring_momentum_score": momentum,
                "matched_sources": sorted(str(x) for x in matched_sources if x),
                "computed_at": datetime.utcnow(),
            }
            ops.append(
                UpdateOne(
                    {"symbol": symbol, "as_of_date": doc["as_of_date"]},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if not ops:
            return 0
        result = self._job_features.bulk_write(ops, ordered=False)  # type: ignore[union-attr]
        return int(result.upserted_count + result.modified_count)

    def get_latest_job_features(self, symbols: List[str]) -> Dict[str, Dict]:
        if not self.enabled or not symbols:
            return {}
        symbol_set = sorted({s for s in symbols if s})
        if not symbol_set:
            return {}
        pipeline = [
            {"$match": {"symbol": {"$in": symbol_set}}},
            {"$sort": {"computed_at": -1}},
            {"$group": {"_id": "$symbol", "doc": {"$first": "$$ROOT"}}},
        ]
        rows = list(self._job_features.aggregate(pipeline))  # type: ignore[union-attr]
        out: Dict[str, Dict] = {}
        for row in rows:
            symbol = str(row.get("_id", "")).strip()
            doc = row.get("doc", {})
            if symbol and isinstance(doc, dict):
                out[symbol] = doc
        return out


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

