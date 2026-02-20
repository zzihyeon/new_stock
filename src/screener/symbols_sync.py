from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import csv
from typing import Dict, List

import requests

KRX_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"


class _KRXTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._in_cell = False
        self._buf: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._in_cell:
            self._current_row.append("".join(self._buf).strip())
            self._in_cell = False
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)


def fetch_symbol_rows() -> List[Dict[str, str]]:
    response = requests.get(KRX_LIST_URL, timeout=30)
    response.raise_for_status()
    html = response.content.decode("euc-kr", errors="ignore")

    parser = _KRXTableParser()
    parser.feed(html)
    if not parser.rows:
        return []

    header = parser.rows[0]
    code_idx = header.index("종목코드") if "종목코드" in header else 2

    code_idx = header.index("종목코드") if "종목코드" in header else 2
    name_idx = header.index("회사명") if "회사명" in header else 0
    market_idx = header.index("시장구분") if "시장구분" in header else 1

    rows: List[Dict[str, str]] = []
    for row in parser.rows[1:]:
        if len(row) <= max(code_idx, name_idx, market_idx):
            continue
        code = row[code_idx].zfill(6)
        if code.isdigit():
            rows.append(
                {
                    "symbol": code,
                    "name": row[name_idx].strip(),
                    "market": row[market_idx].strip(),
                }
            )
    unique = {item["symbol"]: item for item in rows}
    return [unique[k] for k in sorted(unique.keys())]


def save_symbols(symbols: List[str], output_path: str = "data/symbols.txt") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# KRX listed symbols (auto-generated)"] + symbols
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def save_symbols_csv(rows: List[Dict[str, str]], output_path: str = "data/symbols.csv") -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "name", "market"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> None:
    rows = fetch_symbol_rows()
    symbols = [row["symbol"] for row in rows]
    out_txt = save_symbols(symbols)
    out_csv = save_symbols_csv(rows)
    print(f"Saved {len(symbols)} symbols to {out_txt} and {out_csv}")


if __name__ == "__main__":
    main()

