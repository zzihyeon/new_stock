"use client";

import { FormEvent, useEffect, useState } from "react";

import { BacktestPanel } from "@/components/BacktestPanel";
import { CandleChart } from "@/components/CandleChart";
import { ScreenerPanel } from "@/components/ScreenerPanel";
import { WatchlistPanel } from "@/components/WatchlistPanel";

type Candle = {
  baseDate: string;
  baseTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: string;
};

type Timeframe = "DAY" | "MINUTE";

export function StockDashboard() {
  const [symbol, setSymbol] = useState("005930");
  const [timeframe, setTimeframe] = useState<Timeframe>("DAY");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  async function loadCandles(nextSymbol = symbol, refresh = false) {
    if (!nextSymbol) return;
    if (refresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const response = await fetch(
        `/api/candles?symbol=${encodeURIComponent(nextSymbol)}&timeframe=${timeframe}&limit=120${
          refresh ? "&refresh=1" : ""
        }`,
      );
      const payload = await response.json();
      setCandles(payload.candles ?? []);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadCandles().catch(() => {
      setCandles([]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeframe]);

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const nextSymbol = String(formData.get("symbol") || "").toUpperCase().trim();
    setSymbol(nextSymbol);
    loadCandles(nextSymbol).catch(() => {
      setCandles([]);
    });
  }

  async function triggerIngestion() {
    setRefreshing(true);
    try {
      await fetch("/api/ingest", { method: "POST" });
      await loadCandles(symbol, true);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="container">
      <header className="hero">
        <h1>KIS Stock Analyzer</h1>
        <p>Korean stock screening, candle chart, watchlist alerts, and simple backtest.</p>
        <div className="heroActions">
          <button onClick={() => triggerIngestion()} disabled={refreshing}>
            {refreshing ? "Syncing..." : "Run Ingestion"}
          </button>
        </div>
      </header>

      <section className="card">
        <form className="toolbar" onSubmit={onSearch}>
          <label>
            Symbol
            <input name="symbol" defaultValue={symbol} minLength={6} maxLength={12} />
          </label>
          <label>
            Timeframe
            <select
              value={timeframe}
              onChange={(event) => setTimeframe(event.target.value as Timeframe)}
            >
              <option value="DAY">Daily</option>
              <option value="MINUTE">Minute</option>
            </select>
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Loading..." : "Load Chart"}
          </button>
        </form>
      </section>

      <CandleChart candles={candles} symbol={symbol} />
      <ScreenerPanel />
      <WatchlistPanel />
      <BacktestPanel symbol={symbol} />
    </div>
  );
}
