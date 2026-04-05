from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .storage import MongoOHLCVStore


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _extract_total_row(payload: Dict) -> Dict:
    rows = payload.get("list", [])
    if not isinstance(rows, list) or not rows:
        return {}
    for row in rows:
        if str(row.get("fo_bbm", "")).strip() in {"합계", "총계", "전체"}:
            return row
    return rows[0]


def _decode_csv_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff"):
        raw = raw[1:]
    for encoding in ("cp949", "euc-kr", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _load_report_features(report_path: str) -> List[Dict]:
    path = Path(report_path)
    if not path.exists():
        return []
    text = _decode_csv_text(path)
    if not text:
        return []
    rows = csv.DictReader(io.StringIO(text, newline=""))
    out: List[Dict] = []
    now = datetime.utcnow()
    for row in rows:
        corp_code = str(row.get("corp_code", "")).strip()
        stock_code = str(row.get("stock_code", "")).strip()
        if not corp_code:
            continue
        out.append(
            {
                "corp_code": corp_code,
                "stock_code": stock_code,
                "corp_name": str(row.get("name", "")).strip(),
                "as_of_period": "report_current",
                "grade": str(row.get("grade", "")).strip(),
                "score": _to_float(row.get("score")),
                "emp_yoy": _to_float(row.get("annual_emp_yoy")),
                "totpay_yoy": _to_float(row.get("annual_totpay_yoy")),
                "pay_yoy": _to_float(row.get("annual_pay_yoy")),
                "q3_emp_yoy": _to_float(row.get("q3_emp_yoy")),
                "q3_totpay_yoy": _to_float(row.get("q3_totpay_yoy")),
                "q3_pay_yoy": _to_float(row.get("q3_pay_yoy")),
                "computed_at": now,
                "source": "dart_report_csv",
            }
        )
    return out


def migrate_dart_sqlite_to_mongo(
    store: MongoOHLCVStore,
    sqlite_path: str = "dart/dart_cache.sqlite",
    report_path: str = "dart/report.csv",
    batch_size: int = 500,
) -> Dict[str, int]:
    if not store.enabled:
        return {"raw_rows": 0, "raw_upserts": 0, "feature_upserts": 0}

    db_path = Path(sqlite_path)
    if not db_path.exists():
        return {"raw_rows": 0, "raw_upserts": 0, "feature_upserts": 0}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT corp_code, bsns_year, reprt_code, payload, status, updated_at FROM emp_cache")
    rows = cur.fetchall()

    raw_buffer: List[Dict] = []
    feature_buffer: List[Dict] = []
    raw_upserts = 0
    feature_upserts = 0
    now = datetime.utcnow()

    for corp_code, bsns_year, reprt_code, payload_text, status, updated_at in rows:
        try:
            payload = json.loads(payload_text)
        except (TypeError, json.JSONDecodeError):
            payload = {}
        total = _extract_total_row(payload)
        corp_name = str(total.get("corp_name", "")).strip()
        stock_code = str(total.get("stock_code", "")).strip()
        raw_buffer.append(
            {
                "corp_code": str(corp_code).strip(),
                "bsns_year": int(bsns_year),
                "reprt_code": str(reprt_code).strip(),
                "stock_code": stock_code,
                "corp_name": corp_name,
                "payload": payload,
                "status": str(status or "").strip(),
                "updated_at": int(updated_at or 0),
            }
        )
        if total:
            feature_buffer.append(
                {
                    "corp_code": str(corp_code).strip(),
                    "stock_code": stock_code,
                    "corp_name": corp_name,
                    "as_of_period": f"{int(bsns_year)}_{str(reprt_code).strip()}",
                    "emp_total": _to_float(total.get("sm")),
                    "totpay_total": _to_float(total.get("fyer_salary_totamt")),
                    "avg_salary": _to_float(total.get("jan_salary_am")),
                    "status": str(status or "").strip(),
                    "computed_at": now,
                    "source": "sqlite_emp_cache_payload",
                }
            )

        if len(raw_buffer) >= batch_size:
            raw_upserts += store.upsert_dart_raw(raw_buffer)
            raw_buffer = []
        if len(feature_buffer) >= batch_size:
            feature_upserts += store.upsert_dart_features(feature_buffer)
            feature_buffer = []

    if raw_buffer:
        raw_upserts += store.upsert_dart_raw(raw_buffer)
    if feature_buffer:
        feature_upserts += store.upsert_dart_features(feature_buffer)

    report_features = _load_report_features(report_path)
    if report_features:
        feature_upserts += store.upsert_dart_features(report_features)

    conn.close()
    return {
        "raw_rows": len(rows),
        "raw_upserts": raw_upserts,
        "feature_upserts": feature_upserts,
    }

