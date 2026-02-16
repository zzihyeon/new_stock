import { Timeframe } from "@prisma/client";
import { NextRequest } from "next/server";
import { z } from "zod";

import { runSimpleSmaBacktest } from "@/lib/backtest";
import { prisma } from "@/lib/db";
import { jsonWithBigInt } from "@/lib/http";

const requestSchema = z.object({
  symbol: z.string().min(6).max(12),
  fromDate: z.string().regex(/^\d{8}$/),
  toDate: z.string().regex(/^\d{8}$/),
  initialCapital: z.number().positive().default(10000000),
  shortPeriod: z.number().int().min(2).max(30).default(5),
  longPeriod: z.number().int().min(5).max(120).default(20),
});

export async function POST(request: NextRequest) {
  const payload = await request.json().catch(() => ({}));
  const parsed = requestSchema.safeParse(payload);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  const input = parsed.data;
  const candles = await prisma.candle.findMany({
    where: {
      symbol: input.symbol.toUpperCase(),
      timeframe: Timeframe.DAY,
      baseDate: { gte: input.fromDate, lte: input.toDate },
    },
    select: { baseDate: true, close: true },
    orderBy: { baseDate: "asc" },
  });

  if (candles.length < input.longPeriod + 5) {
    return jsonWithBigInt(
      { error: "Not enough candles for selected period." },
      { status: 400 },
    );
  }

  const result = runSimpleSmaBacktest(
    candles,
    input.initialCapital,
    input.shortPeriod,
    input.longPeriod,
  );

  const saved = await prisma.backtestRun.create({
    data: {
      symbol: input.symbol.toUpperCase(),
      timeframe: Timeframe.DAY,
      fromDate: input.fromDate,
      toDate: input.toDate,
      ruleName: `SMA${input.shortPeriod}/${input.longPeriod}`,
      initialCapital: input.initialCapital,
      finalCapital: result.finalCapital,
      totalReturnPct: result.totalReturnPct,
      maxDrawdownPct: result.maxDrawdownPct,
      trades: result.trades,
      summary: result.equityCurve.slice(-60),
    },
  });

  return jsonWithBigInt({ runId: saved.id, result });
}
