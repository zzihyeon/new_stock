"use client";

import { FormEvent, useEffect, useState } from "react";

type WatchlistItem = {
  id: string;
  symbol: string;
  memo: string | null;
  targetPrice: number | null;
  stopPrice: number | null;
  enabled: boolean;
};

export function WatchlistPanel() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    const res = await fetch("/api/watchlist", { cache: "no-store" });
    const payload = await res.json();
    setItems(payload.items ?? []);
  }

  useEffect(() => {
    load().catch(() => {
      setItems([]);
    });
  }, []);

  async function onAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setLoading(true);
    try {
      await fetch("/api/watchlist", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          symbol: String(formData.get("symbol") || "").toUpperCase(),
          memo: String(formData.get("memo") || ""),
          targetPrice: Number(formData.get("targetPrice") || 0) || undefined,
          stopPrice: Number(formData.get("stopPrice") || 0) || undefined,
        }),
      });
      event.currentTarget.reset();
      await load();
    } finally {
      setLoading(false);
    }
  }

  async function onDelete(id: string) {
    await fetch(`/api/watchlist?id=${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <section className="card">
      <h3>Watchlist & Alerts</h3>
      <form className="gridForm" onSubmit={onAdd}>
        <label>
          Symbol
          <input name="symbol" defaultValue="005930" minLength={6} maxLength={12} />
        </label>
        <label>
          Memo
          <input name="memo" placeholder="Earnings theme, breakout..." />
        </label>
        <label>
          Target Price
          <input name="targetPrice" type="number" min={0} />
        </label>
        <label>
          Stop Price
          <input name="stopPrice" type="number" min={0} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Adding..." : "Add Item"}
        </button>
      </form>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Target</th>
              <th>Stop</th>
              <th>Memo</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.symbol}</td>
                <td>{item.targetPrice?.toLocaleString() ?? "-"}</td>
                <td>{item.stopPrice?.toLocaleString() ?? "-"}</td>
                <td>{item.memo || "-"}</td>
                <td>
                  <button className="danger" onClick={() => onDelete(item.id)} type="button">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="mutedCell">
                  No watchlist items.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
