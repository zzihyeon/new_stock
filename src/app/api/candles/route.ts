import { Timeframe } from "@prisma/client";
import { NextRequest } from "next/server";

import { prisma } from "@/lib/db";
import { jsonWithBigInt } from "@/lib/http";
import { fetchDailyCandles, fetchMinuteCandles } from "@/lib/kis/client";

function parseTimeframe(value: string | null): Timeframe {
  return value?.toUpperCase() === "MINUTE" ? Timeframe.MINUTE : Timeframe.DAY;
}

async function backfill(symbol: string, timeframe: Timeframe) {
  const candles =
    timeframe === Timeframe.DAY
      ? await fetchDailyCandles(symbol)
      : await fetchMinuteCandles(symbol);

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

  let candles = await prisma.candle.findMany({
    where: { symbol, timeframe },
    orderBy: [{ baseDate: "desc" }, { baseTime: "desc" }],
    take: Math.min(Math.max(limit, 10), 300),
  });

  if (candles.length === 0) {
    await backfill(symbol, timeframe);
    candles = await prisma.candle.findMany({
      where: { symbol, timeframe },
      orderBy: [{ baseDate: "desc" }, { baseTime: "desc" }],
      take: Math.min(Math.max(limit, 10), 300),
    });
  }

  return jsonWithBigInt({
    symbol,
    timeframe,
    count: candles.length,
    candles: candles.reverse(),
  });
}
