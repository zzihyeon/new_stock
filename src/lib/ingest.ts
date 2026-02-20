import { CandleModel, StockModel, Timeframe } from "@/lib/models";
import { connectMongo } from "@/lib/mongodb";
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
  await connectMongo();
  let written = 0;
  for (const candle of candles) {
    if (!candle.baseDate) {
      continue;
    }
    await CandleModel.updateOne(
      { symbol, timeframe, baseDate: candle.baseDate, baseTime: candle.baseTime },
      {
        $set: {
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
          volume: Number(candle.volume),
          tradeValue: candle.tradeValue ? Number(candle.tradeValue) : undefined,
        },
      },
      { upsert: true },
    );
    written += 1;
  }
  return written;
}

export async function runDefaultIngestion(): Promise<IngestSummary[]> {
  await connectMongo();
  const summaries: IngestSummary[] = [];

  for (const item of DEFAULT_SYMBOLS) {
    await StockModel.updateOne(
      { symbol: item.symbol },
      { $set: { symbol: item.symbol, name: item.name, market: item.market } },
      { upsert: true },
    );

    const [dailyCandles, minuteCandles] = await Promise.all([
      fetchDailyCandles(item.symbol),
      fetchMinuteCandles(item.symbol),
    ]);

    const daily = await upsertCandles(item.symbol, "DAY", dailyCandles);
    const minute = await upsertCandles(item.symbol, "MINUTE", minuteCandles);
    summaries.push({ symbol: item.symbol, daily, minute });
  }

  return summaries;
}
