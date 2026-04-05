from __future__ import annotations

import hashlib
import html as htmllib
import random
import re
import time
from datetime import datetime
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import quote_plus, urljoin

import requests

from .storage import MongoOHLCVStore


def _chunked(items: Sequence[Tuple[str, str]], size: int) -> Iterable[Sequence[Tuple[str, str]]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _normalize_company_name(name: str) -> str:
    value = (name or "").strip().upper()
    if not value:
        return ""
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"(주식회사|\(주\)|㈜)", "", value)
    return value


def _build_symbol_lookup(symbol_name_map: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for symbol, name in symbol_name_map.items():
        key = _normalize_company_name(name)
        if key and key not in out:
            out[key] = symbol
    return out


def _extract_date(text: str) -> datetime:
    if not text:
        return datetime.utcnow()
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if not m:
        return datetime.utcnow()
    y, mth, d = m.groups()
    try:
        return datetime(int(y), int(mth), int(d))
    except ValueError:
        return datetime.utcnow()


def _parse_saramin(page_html: str, company_name: str, fallback_symbol: str) -> List[Dict]:
    postings: List[Dict] = []
    pattern = re.compile(
        r'<h2[^>]*class="job_tit"[^>]*>.*?<a[^>]+href="(?P<href>[^"]*rec_idx=\d+[^"]*)"[^>]*title="(?P<title>[^"]+)"',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page_html):
        href = htmllib.unescape(match.group("href"))
        title = re.sub(r"\s+", " ", htmllib.unescape(match.group("title"))).strip()
        if not href or not title:
            continue
        url = urljoin("https://www.saramin.co.kr", href)
        external_id = hashlib.sha1(f"saramin|{url}".encode("utf-8")).hexdigest()
        postings.append(
            {
                "source": "saramin",
                "external_id": external_id,
                "symbol": fallback_symbol,
                "company_name_raw": company_name,
                "normalized_company": _normalize_company_name(company_name),
                "title": title,
                "posted_at": "",
                "posted_at_dt": datetime.utcnow(),
                "deadline": "",
                "url": url,
                "location": "",
                "keywords": [],
            }
        )
    return postings


def _parse_jobkorea(page_html: str, company_name: str, fallback_symbol: str) -> List[Dict]:
    postings: List[Dict] = []
    pattern = re.compile(
        r'<a[^>]+href="(?P<href>/Recruit/GI_Read/\d+[^"]*)"[^>]*>(?P<title>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(page_html):
        href = htmllib.unescape(match.group("href"))
        title = re.sub(r"<[^>]+>", " ", htmllib.unescape(match.group("title")))
        title = re.sub(r"\s+", " ", title).strip()
        if not href or not title:
            continue
        url = urljoin("https://www.jobkorea.co.kr", href)
        external_id = hashlib.sha1(f"jobkorea|{url}".encode("utf-8")).hexdigest()
        postings.append(
            {
                "source": "jobkorea",
                "external_id": external_id,
                "symbol": fallback_symbol,
                "company_name_raw": company_name,
                "normalized_company": _normalize_company_name(company_name),
                "title": title,
                "posted_at": "",
                "posted_at_dt": datetime.utcnow(),
                "deadline": "",
                "url": url,
                "location": "",
                "keywords": [],
            }
        )
    return postings


def _fetch_source_html(source: str, company_name: str, timeout: int = 12) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        )
    }
    if source == "saramin":
        url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={quote_plus(company_name)}"
    elif source == "jobkorea":
        url = f"https://www.jobkorea.co.kr/Search/?stext={quote_plus(company_name)}"
    else:
        return ""
    res = requests.get(url, timeout=timeout, headers=headers)
    if res.status_code != 200:
        return ""
    return res.text


def collect_jobs_and_update_features(
    store: MongoOHLCVStore,
    symbol_name_map: Dict[str, str],
    sources: Sequence[str],
    max_companies: int = 120,
    request_interval: float = 0.4,
) -> Dict[str, int]:
    if not store.enabled:
        return {"requested": 0, "posting_upserts": 0, "feature_upserts": 0}

    selected: List[Tuple[str, str]] = []
    for symbol, name in symbol_name_map.items():
        if symbol and name:
            selected.append((symbol, name))
    selected = selected[: max(max_companies, 0)]

    postings: List[Dict] = []
    for symbol, company_name in selected:
        for source in sources:
            source_key = source.strip().lower()
            if source_key not in {"saramin", "jobkorea"}:
                continue
            try:
                html = _fetch_source_html(source_key, company_name)
                if source_key == "saramin":
                    parsed = _parse_saramin(html, company_name, symbol)
                else:
                    parsed = _parse_jobkorea(html, company_name, symbol)
                postings.extend(parsed[:15])
            except Exception:
                continue
            time.sleep(max(request_interval, 0.05) + random.random() * 0.2)

    # Deduplicate by source/external_id pair before write.
    unique_map: Dict[Tuple[str, str], Dict] = {}
    for row in postings:
        key = (str(row.get("source", "")), str(row.get("external_id", "")))
        if key[0] and key[1]:
            unique_map[key] = row

    posting_upserts = store.upsert_job_postings(list(unique_map.values()))
    feature_upserts = store.recompute_job_features()
    return {
        "requested": len(selected) * len([s for s in sources if s.strip().lower() in {"saramin", "jobkorea"}]),
        "posting_upserts": posting_upserts,
        "feature_upserts": feature_upserts,
    }

