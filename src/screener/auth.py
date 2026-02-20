from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


def load_dotenv(dotenv_path: str = ".env") -> None:
    """Tiny dotenv loader to avoid extra dependency in runtime."""
    path = Path(dotenv_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str
    product_code: str
    base_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    mongodb_uri: str
    mongodb_db_name: str


def load_config() -> KISConfig:
    load_dotenv(".env")

    app_key = os.getenv("APP_KEY") or os.getenv("KIS_APP_KEY", "")
    app_secret = os.getenv("APP_SECRET") or os.getenv("KIS_APP_SECRET", "")
    account_no = os.getenv("ACCOUNT") or os.getenv("KIS_ACCOUNT_NO", "")
    product_code = os.getenv("ACCOUNT_PRODUCT_CODE") or os.getenv("KIS_PRODUCT_CODE", "01")
    base_url = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=replDb")
    mongodb_db_name = os.getenv("MONGODB_DB_NAME", "stock")

    if not app_key or not app_secret:
        raise ValueError("APP_KEY(APP_KEY/KIS_APP_KEY) and APP_SECRET(APP_SECRET/KIS_APP_SECRET) are required.")

    return KISConfig(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        product_code=product_code,
        base_url=base_url,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        mongodb_uri=mongodb_uri,
        mongodb_db_name=mongodb_db_name,
    )


class KISTokenProvider:
    def __init__(self, config: KISConfig, cache_path: str = ".cache/kis_token.json") -> None:
        self.config = config
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._in_memory_token: Optional[str] = None
        self._in_memory_expires_at: float = 0.0

    def get_token(self, force_refresh: bool = False) -> str:
        now = time.time()

        if not force_refresh and self._in_memory_token and self._in_memory_expires_at > now + 30:
            return self._in_memory_token

        if not force_refresh:
            cached = self._read_cache()
            if cached and cached["expires_at"] > now + 30:
                self._in_memory_token = cached["token"]
                self._in_memory_expires_at = cached["expires_at"]
                return cached["token"]

        token, expires_in = self._request_new_token()
        expires_at = now + int(expires_in)

        self._in_memory_token = token
        self._in_memory_expires_at = expires_at
        self._write_cache(token, expires_at)
        return token

    def _request_new_token(self) -> tuple[str, int]:
        url = f"{self.config.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }

        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            body = response.text.strip()
            raise RuntimeError(f"KIS token request failed: {response.status_code} {body}")

        data = response.json()
        return data["access_token"], int(data.get("expires_in", 3600))

    def _read_cache(self) -> Optional[dict]:
        if not self.cache_path.exists():
            return None
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if "token" in data and "expires_at" in data:
                return data
        except (json.JSONDecodeError, OSError):
            return None
        return None

    def _write_cache(self, token: str, expires_at: float) -> None:
        payload = {"token": token, "expires_at": expires_at}
        self.cache_path.write_text(json.dumps(payload), encoding="utf-8")

