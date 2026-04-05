from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests


def print_console_table(rows: List[Dict]) -> None:
    if not rows:
        print("No candidates found.")
        return

    header = f"{'Rank':<6}{'Symbol':<10}{'Name':<16}{'Pattern':<20}{'Close':<12}{'Date':<12}{'Risk':<24}"
    print(header)
    print("-" * len(header))
    for idx, row in enumerate(rows, start=1):
        risk = ",".join(row.get("risk_flags", [])) or "-"
        print(
            f"{idx:<6}{row['symbol']:<10}{row.get('name', row['symbol']):<16}{row['pattern']:<20}{row['close']:<12}{row['latest_date']:<12}{risk:<24}"
        )


def save_csv(rows: List[Dict], output_dir: str = "reports") -> Optional[Path]:
    if not rows:
        return None

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out = Path(output_dir) / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fields = [
        "screen_mode",
        "symbol",
        "name",
        "pattern",
        "close",
        "latest_date",
        "latest_volume",
        "market_cap",
        "technical_score",
        "dart_grade",
        "dart_score",
        "hiring_momentum_score",
        "hiring_posting_count_7d",
        "hiring_posting_count_30d",
        "composite_score",
        "manual_review",
        "risk_flags",
        "details",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "risk_flags": "|".join(row.get("risk_flags", [])),
                    "details": json.dumps(row.get("details", {}), ensure_ascii=False),
                }
            )
    return out


def save_universe_list(symbols: List[str], output_path: str = "data/universe_100b.txt") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Market-cap >= 100 billion KRW (auto-generated)"] + sorted(set(symbols))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_top5_summary(rows: List[Dict]) -> None:
    print("\n[Top 5 Summary]")
    for row in rows[:5]:
        pattern = row["pattern"]
        details = row.get("details", {})
        support = ",".join(details.get("support_reasons", []))
        print(
            f"- {row['symbol']}({row.get('name', row['symbol'])}) | {pattern} | close={row['close']} | support={support or '-'}"
        )


def read_previous_symbols(state_path: str = ".cache/last_candidates.json") -> Set[str]:
    path = Path(state_path)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("symbols", []))
    except json.JSONDecodeError:
        return set()


def save_current_symbols(symbols: Set[str], state_path: str = ".cache/last_candidates.json") -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"symbols": sorted(symbols), "updated_at": datetime.now().isoformat()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def new_inclusions(rows: List[Dict], old_symbols: Set[str]) -> List[Dict]:
    return [row for row in rows if row["symbol"] not in old_symbols]


def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)


def notify_new_inclusions(rows: List[Dict], bot_token: str, chat_id: str) -> None:
    if not rows:
        return
    lines = ["[KIS Screener] New inclusions detected"]
    for row in rows[:10]:
        lines.append(
            f"- {row['symbol']}({row.get('name', row['symbol'])}) | {row['pattern']} | close={row['close']} | date={row['latest_date']}"
        )
    send_telegram(bot_token, chat_id, "\n".join(lines))


def notify_full_watchlist(rows: List[Dict], bot_token: str, chat_id: str, title: str = "[KIS Screener] Watchlist") -> None:
    if not bot_token or not chat_id:
        return
    lines = [title]
    if not rows:
        lines.append("- 조건 충족 종목 없음")
    else:
        for i, row in enumerate(rows[:20], start=1):
            lines.append(
                f"{i}) {row['symbol']}({row.get('name', row['symbol'])}) | {row['pattern']} | close={row['close']} | vol={row.get('latest_volume', 0)}"
            )
    send_telegram(bot_token, chat_id, "\n".join(lines))

