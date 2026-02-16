"use client";

import { FormEvent, useState } from "react";

type ScreenerRow = {
  symbol: string;
  name: string;
  close: number;
  volume: string;
  changeRate: number;
  baseDate: string;
};

type ScreenerResponse = {
  count: number;
  rows: ScreenerRow[];
};

export function ScreenerPanel() {
  const [rows, setRows] = useState<ScreenerRow[]>([]);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);

    setLoading(true);
    try {
      const response = await fetch("/api/screener", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          minPrice: Number(formData.get("minPrice") || 0) || undefined,
          maxPrice: Number(formData.get("maxPrice") || 0) || undefined,
          minVolume: Number(formData.get("minVolume") || 0) || undefined,
          minChangeRate: Number(formData.get("minChangeRate") || 0) || undefined,
        }),
      });

      const payload = (await response.json()) as ScreenerResponse;
      setRows(payload.rows ?? []);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h3>Stock Screener</h3>
      <form className="gridForm" onSubmit={onSubmit}>
        <label>
          Min Price
          <input name="minPrice" type="number" min="0" step="1" />
        </label>
        <label>
          Max Price
          <input name="maxPrice" type="number" min="0" step="1" />
        </label>
        <label>
          Min Volume
          <input name="minVolume" type="number" min="0" step="1" />
        </label>
        <label>
          Min Change(%)
          <input name="minChangeRate" type="number" step="0.1" />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Searching..." : "Run Screener"}
        </button>
      </form>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Close</th>
              <th>Volume</th>
              <th>Change%</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.symbol}-${row.baseDate}`}>
                <td>{row.symbol}</td>
                <td>{row.name}</td>
                <td>{row.close.toLocaleString()}</td>
                <td>{Number(row.volume).toLocaleString()}</td>
                <td className={row.changeRate >= 0 ? "up" : "down"}>
                  {row.changeRate.toFixed(2)}
                </td>
                <td>{row.baseDate}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="mutedCell">
                  No results. Run the screener after ingestion.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
