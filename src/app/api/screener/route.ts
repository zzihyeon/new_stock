import { NextRequest } from "next/server";
import { z } from "zod";

import { jsonWithBigInt } from "@/lib/http";
import { CandleModel, StockModel } from "@/lib/models";
import { connectMongo } from "@/lib/mongodb";

const screenerSchema = z.object({
  minPrice: z.number().int().nonnegative().optional(),
  maxPrice: z.number().int().nonnegative().optional(),
  minVolume: z.number().int().nonnegative().optional(),
  minChangeRate: z.number().optional(),
});

type ScreenerRow = {
  symbol: string;
  name: string;
  close: number;
  volume: number;
  open: number;
  changeRate: number;
  baseDate: string;
};

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const parsed = screenerSchema.safeParse(body);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  const filters = parsed.data;
  await connectMongo();

  const latestBySymbol = await CandleModel.aggregate<{ symbol: string; maxDateTime: string }>([
    { $match: { timeframe: "DAY" } },
    {
      $addFields: {
        dateTimeKey: { $concat: ["$baseDate", "$baseTime"] },
      },
    },
    { $sort: { dateTimeKey: -1 } },
    { $group: { _id: "$symbol", maxDateTime: { $first: "$dateTimeKey" } } },
    { $project: { _id: 0, symbol: "$_id", maxDateTime: 1 } },
  ]);

  const symbolSet = new Set(latestBySymbol.map((x) => x.symbol));
  const candles = await CandleModel.find({
    timeframe: "DAY",
    symbol: { $in: Array.from(symbolSet) },
  })
    .sort({ baseDate: -1, baseTime: -1 })
    .lean();

  const stockDocs = await StockModel.find({ symbol: { $in: Array.from(symbolSet) } }).lean();
  const stockNameMap = new Map(stockDocs.map((item) => [item.symbol, item.name]));
  const latestMap = new Map(latestBySymbol.map((item) => [item.symbol, item.maxDateTime]));
  const seen = new Set<string>();

  const rows: ScreenerRow[] = [];
  for (const c of candles) {
    if (seen.has(c.symbol)) continue;
    const key = `${c.baseDate}${c.baseTime}`;
    if (latestMap.get(c.symbol) !== key) continue;
    seen.add(c.symbol);
    const changeRate = c.open === 0 ? 0 : Number((((c.close - c.open) / c.open) * 100).toFixed(2));
    rows.push({
      symbol: c.symbol,
      name: stockNameMap.get(c.symbol) ?? c.symbol,
      close: c.close,
      open: c.open,
      volume: c.volume,
      changeRate,
      baseDate: c.baseDate,
    });
  }

  const filtered = rows
    .filter((row) => (typeof filters.minPrice === "number" ? row.close >= filters.minPrice : true))
    .filter((row) => (typeof filters.maxPrice === "number" ? row.close <= filters.maxPrice : true))
    .filter((row) => (typeof filters.minVolume === "number" ? row.volume >= filters.minVolume : true))
    .filter((row) =>
      typeof filters.minChangeRate === "number" ? row.changeRate >= filters.minChangeRate : true,
    )
    .sort((a, b) => b.volume - a.volume)
    .slice(0, 100);

  return jsonWithBigInt({ count: filtered.length, rows: filtered });
}
