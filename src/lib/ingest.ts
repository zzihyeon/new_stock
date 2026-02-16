import { Timeframe } from "@prisma/client";

import { prisma } from "@/lib/db";
import { fetchDailyCandles, fetchMinuteCandles } from "@/lib/kis/client";

const DEFAULT_SYMBOLS = [
  { symbol: "005930", name: "SamsungElectronics", market: "KOSPI" },
  { symbol: "000660", name: "SKHynix", market: "KOSPI" },
  { symbol: "035420", name: "NAVER", market: "KOSPI" },
  { symbol: "035720", name: "Kakao", market: "KOSPI" },
];

type IngestSummary = {
  symbol: string;
  daily: number;
  minute: number;
};

async function upsertCandles(
  symbol: string,
  timeframe: Timeframe,
  candles: Awaited<ReturnType<typeof fetchDailyCandles>>,
): Promise<number> {
  let written = 0;
  for (const candle of candles) {
    if (!candle.baseDate) {
      continue;
    }
    await prisma.candle.upsert({
      where: {
        symbol_timeframe_baseDate_baseTime: {
          symbol,
          timeframe,
          baseDate: candle.baseDate,
          baseTime: candle.baseTime,
        },
      },
      update: {
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
        tradeValue: candle.tradeValue,
      },
      create: {
        symbol,
        timeframe,
        baseDate: candle.baseDate,
        baseTime: candle.baseTime,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
        tradeValue: candle.tradeValue,
      },
    });
    written += 1;
  }
  return written;
}

export async function runDefaultIngestion(): Promise<IngestSummary[]> {
  const summaries: IngestSummary[] = [];

  for (const item of DEFAULT_SYMBOLS) {
    await prisma.stock.upsert({
      where: { symbol: item.symbol },
      update: { name: item.name, market: item.market },
      create: { symbol: item.symbol, name: item.name, market: item.market },
    });

    const [dailyCandles, minuteCandles] = await Promise.all([
      fetchDailyCandles(item.symbol),
      fetchMinuteCandles(item.symbol),
    ]);

    const daily = await upsertCandles(item.symbol, Timeframe.DAY, dailyCandles);
    const minute = await upsertCandles(item.symbol, Timeframe.MINUTE, minuteCandles);
    summaries.push({ symbol: item.symbol, daily, minute });
  }

  return summaries;
}
