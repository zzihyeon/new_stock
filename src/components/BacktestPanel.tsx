"use client";

import { FormEvent, useMemo, useState } from "react";

type BacktestResult = {
  initialCapital: number;
  finalCapital: number;
  totalReturnPct: number;
  maxDrawdownPct: number;
  trades: number;
  equityCurve: Array<{ date: string; equity: number }>;
};

export function BacktestPanel({ symbol }: { symbol: string }) {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const defaultFrom = "20240101";
  const defaultTo = useMemo(() => {
    const now = new Date();
    return `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(
      now.getDate(),
    ).padStart(2, "0")}`;
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setLoading(true);

    try {
      const response = await fetch("/api/backtest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          symbol,
          fromDate: String(formData.get("fromDate")),
          toDate: String(formData.get("toDate")),
          initialCapital: Number(formData.get("initialCapital")),
          shortPeriod: Number(formData.get("shortPeriod")),
          longPeriod: Number(formData.get("longPeriod")),
        }),
      });
      const payload = await response.json();
      setResult(payload.result ?? null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card">
      <h3>Simple Backtest (SMA Cross)</h3>
      <form className="gridForm" onSubmit={onSubmit}>
        <label>
          From (YYYYMMDD)
          <input name="fromDate" defaultValue={defaultFrom} pattern="\d{8}" />
        </label>
        <label>
          To (YYYYMMDD)
          <input name="toDate" defaultValue={defaultTo} pattern="\d{8}" />
        </label>
        <label>
          Initial Capital
          <input name="initialCapital" type="number" defaultValue={10000000} />
        </label>
        <label>
          Short SMA
          <input name="shortPeriod" type="number" defaultValue={5} min={2} max={30} />
        </label>
        <label>
          Long SMA
          <input name="longPeriod" type="number" defaultValue={20} min={5} max={120} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Running..." : "Run Backtest"}
        </button>
      </form>
      {result && (
        <div className="metrics">
          <div>
            <span>Final Capital</span>
            <strong>{Math.round(result.finalCapital).toLocaleString()}</strong>
          </div>
          <div>
            <span>Total Return</span>
            <strong className={result.totalReturnPct >= 0 ? "up" : "down"}>
              {result.totalReturnPct.toFixed(2)}%
            </strong>
          </div>
          <div>
            <span>Max Drawdown</span>
            <strong className="down">{result.maxDrawdownPct.toFixed(2)}%</strong>
          </div>
          <div>
            <span>Trades</span>
            <strong>{result.trades}</strong>
          </div>
        </div>
      )}
    </section>
  );
}
