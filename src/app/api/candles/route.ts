import { NextRequest } from "next/server";

import { jsonWithBigInt } from "@/lib/http";
import { fetchDailyCandles, fetchMinuteCandles } from "@/lib/kis/client";
import { CandleModel, Timeframe } from "@/lib/models";
import { connectMongo } from "@/lib/mongodb";

function parseTimeframe(value: string | null): Timeframe {
  return value?.toUpperCase() === "MINUTE" ? "MINUTE" : "DAY";
}

async function backfill(symbol: string, timeframe: Timeframe) {
  const candles =
    timeframe === "DAY"
      ? await fetchDailyCandles(symbol)
      : await fetchMinuteCandles(symbol);

  await connectMongo();
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
  }
}

export async function GET(request: NextRequest) {
  const symbol = request.nextUrl.searchParams.get("symbol") ?? "";
  const timeframe = parseTimeframe(request.nextUrl.searchParams.get("timeframe"));
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? "120");
  const shouldRefresh = request.nextUrl.searchParams.get("refresh") === "1";

  if (!symbol) {
    return jsonWithBigInt({ error: "symbol is required" }, { status: 400 });
  }

  if (shouldRefresh) {
    await backfill(symbol, timeframe);
  }

  await connectMongo();
  let candles = await CandleModel.find({ symbol, timeframe })
    .sort({ baseDate: -1, baseTime: -1 })
    .limit(Math.min(Math.max(limit, 10), 300))
    .lean();

  if (candles.length === 0) {
    await backfill(symbol, timeframe);
    candles = await CandleModel.find({ symbol, timeframe })
      .sort({ baseDate: -1, baseTime: -1 })
      .limit(Math.min(Math.max(limit, 10), 300))
      .lean();
  }

  return jsonWithBigInt({
    symbol,
    timeframe,
    count: candles.length,
    candles: candles.reverse(),
  });
}
