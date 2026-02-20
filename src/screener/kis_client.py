from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .auth import KISConfig, KISTokenProvider
from .kis_official_specs import (
    INQUIRE_DAILY_ITEMCHART_API_URL,
    INQUIRE_DAILY_ITEMCHART_TR_ID,
    INQUIRE_DAILY_PRICE_API_URL,
    INQUIRE_DAILY_PRICE_TR_ID,
    INQUIRE_PRICE_API_URL,
    INQUIRE_PRICE_TR_ID,
)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return default


class HTTPCache:
    def __init__(self, cache_dir: str = ".cache/http", ttl_seconds: int = 60) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[dict]:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def set(self, key: str, payload: dict) -> None:
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def build_key(url: str, params: Dict[str, str], tr_id: str) -> str:
        raw = f"{url}|{tr_id}|{json.dumps(params, sort_keys=True)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class KISClient:
    def __init__(
        self,
        config: KISConfig,
        token_provider: KISTokenProvider,
        request_interval_seconds: float = 0.12,
        cache_ttl_seconds: int = 60,
    ) -> None:
        self.config = config
        self.token_provider = token_provider
        self.request_interval_seconds = request_interval_seconds
        self.cache = HTTPCache(ttl_seconds=cache_ttl_seconds)
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        delta = time.time() - self._last_request_at
        if delta < self.request_interval_seconds:
            time.sleep(self.request_interval_seconds - delta)
        self._last_request_at = time.time()

    def _get(self, path: str, tr_id: str, params: Dict[str, str], use_cache: bool = True) -> dict:
        url = f"{self.config.base_url}{path}"
        cache_key = self.cache.build_key(url, params, tr_id)
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        self._throttle()
        token = self.token_provider.get_token(force_refresh=False)
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

        response = requests.get(url, headers=headers, params=params, timeout=12)
        if response.status_code == 401:
            token = self.token_provider.get_token(force_refresh=True)
            headers["authorization"] = f"Bearer {token}"
            response = requests.get(url, headers=headers, params=params, timeout=12)

        if response.status_code != 200:
            raise RuntimeError(f"KIS GET failed {response.status_code}: {response.text}")

        payload = response.json()
        rt_cd = payload.get("rt_cd")
        if rt_cd not in (None, "", "0"):
            msg = payload.get("msg1", "unknown error")
            raise RuntimeError(f"KIS business error: {msg}")

        if use_cache:
            self.cache.set(cache_key, payload)
        return payload

    def get_daily_ohlcv(self, symbol: str, period_code: str = "D") -> List[dict]:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_PERIOD_DIV_CODE": period_code,
            "FID_ORG_ADJ_PRC": "0",
        }

        payload = self._get(
            INQUIRE_DAILY_ITEMCHART_API_URL,
            INQUIRE_DAILY_ITEMCHART_TR_ID,
            params,
            use_cache=True,
        )
        rows = payload.get("output2") or payload.get("output1") or payload.get("output") or []

        # Some accounts return empty payload for itemchart endpoint.
        # Fallback to daily-price endpoint for stable daily OHLCV.
        if not rows:
            payload = self._get(
                INQUIRE_DAILY_PRICE_API_URL,
                INQUIRE_DAILY_PRICE_TR_ID,
                params,
                use_cache=True,
            )
            rows = payload.get("output") or []

        # Last retry without cache for transient empty responses.
        if not rows:
            payload = self._get(
                INQUIRE_DAILY_PRICE_API_URL,
                INQUIRE_DAILY_PRICE_TR_ID,
                params,
                use_cache=False,
            )
            rows = payload.get("output") or []

        normalized = [
            {
                "date": row.get("stck_bsop_date", ""),
                "open": _to_int(row.get("stck_oprc")),
                "high": _to_int(row.get("stck_hgpr")),
                "low": _to_int(row.get("stck_lwpr")),
                "close": _to_int(row.get("stck_clpr")),
                "volume": _to_int(row.get("acml_vol")),
                "trading_value": _to_int(row.get("acml_tr_pbmn"))
                or (_to_int(row.get("stck_clpr")) * _to_int(row.get("acml_vol"))),
            }
            for row in rows
            if row.get("stck_bsop_date")
        ]
        return sorted(normalized, key=lambda x: x["date"])

    def get_price_snapshot(self, symbol: str) -> dict:
        payload = self._get(
            INQUIRE_PRICE_API_URL,
            INQUIRE_PRICE_TR_ID,
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
            use_cache=False,
        )
        out = payload.get("output", {})
        listed_shares = _to_int(out.get("lstn_stcn"))
        close_price = _to_int(out.get("stck_prpr"))
        market_cap_eok = _to_int(out.get("hts_avls"))

        market_cap_from_eok = market_cap_eok * 100_000_000 if market_cap_eok > 0 else 0
        market_cap_from_shares = listed_shares * close_price if listed_shares > 0 and close_price > 0 else 0
        market_cap = market_cap_from_eok or market_cap_from_shares

        return {
            "symbol": symbol,
            "name": out.get("hts_kor_isnm", "").strip(),
            "close": close_price,
            "volume": _to_int(out.get("acml_vol")),
            "listed_shares": listed_shares,
            "market_cap_eok": market_cap_eok,
            "market_cap": market_cap,
        }

    def get_market_cap(self, symbol: str, daily_rows: Optional[List[dict]] = None) -> int:
        # If daily row provides market cap-like fields they should be preferred.
        if daily_rows:
            row = daily_rows[0]
            if "market_cap" in row and row["market_cap"] > 0:
                return int(row["market_cap"])
        snapshot = self.get_price_snapshot(symbol)
        return snapshot.get("market_cap", 0)

    def get_financial_proxy(self, symbol: str) -> dict:
        """
        KIS fundamental endpoints vary by product policy.
        This method returns a normalized proxy payload with graceful fallback.
        """
        try:
            payload = self._get(
                "/uapi/domestic-stock/v1/finance/financial-ratio",
                "FHKST66430300",
                {"FID_DIV_CLS_CODE": "0", "fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol},
                use_cache=True,
            )
            rows = payload.get("output") or []
            if not rows:
                return {
                    "op_income_growth": 0.0,
                    "sales_growth": 0.0,
                    "margin_change": 0.0,
                    "ocf_growth": 0.0,
                    "risk_flags": ["FUNDAMENTAL_DATA_MISSING"],
                }
            latest = rows[0]
            normalized = {
                "op_income_growth": float(latest.get("grs", 0) or 0),
                "sales_growth": float(latest.get("sale_grow_rate", 0) or 0),
                "margin_change": float(latest.get("op_prft_rate", 0) or 0),
                "ocf_growth": float(latest.get("cf", 0) or 0),
                "risk_flags": [],
            }
            if (
                normalized["op_income_growth"] == 0.0
                and normalized["sales_growth"] == 0.0
                and normalized["margin_change"] == 0.0
                and normalized["ocf_growth"] == 0.0
            ):
                normalized["risk_flags"] = ["FUNDAMENTAL_DATA_MISSING"]
            return normalized
        except Exception:
            return {
                "op_income_growth": 0.0,
                "sales_growth": 0.0,
                "margin_change": 0.0,
                "ocf_growth": 0.0,
                "risk_flags": ["FUNDAMENTAL_DATA_MISSING"],
            }

