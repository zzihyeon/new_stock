import { NextRequest } from "next/server";
import { z } from "zod";

import { jsonWithBigInt } from "@/lib/http";
import { StockModel, WatchlistItemModel } from "@/lib/models";
import { connectMongo } from "@/lib/mongodb";

const createSchema = z.object({
  symbol: z.string().min(6).max(12),
  memo: z.string().max(200).optional(),
  targetPrice: z.number().int().positive().optional(),
  stopPrice: z.number().int().positive().optional(),
});

const updateSchema = createSchema.partial().extend({
  id: z.string().min(8),
  enabled: z.boolean().optional(),
});

export async function GET() {
  await connectMongo();
  const items = await WatchlistItemModel.find().sort({ createdAt: -1 }).lean();
  const normalized = items.map((item) => ({
    id: item._id.toString(),
    symbol: item.symbol,
    memo: item.memo ?? null,
    targetPrice: item.targetPrice ?? null,
    stopPrice: item.stopPrice ?? null,
    enabled: item.enabled,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
  }));
  return jsonWithBigInt({ count: normalized.length, items: normalized });
}

export async function POST(request: NextRequest) {
  const payload = await request.json().catch(() => ({}));
  const parsed = createSchema.safeParse(payload);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  const symbol = parsed.data.symbol.toUpperCase();
  await connectMongo();
  await StockModel.updateOne(
    { symbol },
    { $setOnInsert: { symbol, name: symbol, market: "KOSPI" } },
    { upsert: true },
  );

  const item = await WatchlistItemModel.create({
    symbol,
    memo: parsed.data.memo,
    targetPrice: parsed.data.targetPrice,
    stopPrice: parsed.data.stopPrice,
    enabled: true,
  });

  return jsonWithBigInt(
    {
      item: {
        id: item._id.toString(),
        symbol: item.symbol,
        memo: item.memo ?? null,
        targetPrice: item.targetPrice ?? null,
        stopPrice: item.stopPrice ?? null,
        enabled: item.enabled,
      },
    },
    { status: 201 },
  );
}

export async function PATCH(request: NextRequest) {
  const payload = await request.json().catch(() => ({}));
  const parsed = updateSchema.safeParse(payload);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  await connectMongo();
  const item = await WatchlistItemModel.findByIdAndUpdate(
    parsed.data.id,
    {
      $set: {
        symbol: parsed.data.symbol?.toUpperCase(),
        memo: parsed.data.memo,
        targetPrice: parsed.data.targetPrice,
        stopPrice: parsed.data.stopPrice,
        enabled: parsed.data.enabled,
      },
    },
    { new: true },
  ).lean();

  return jsonWithBigInt({
    item: item
      ? {
        id: item._id.toString(),
        symbol: item.symbol,
        memo: item.memo ?? null,
        targetPrice: item.targetPrice ?? null,
        stopPrice: item.stopPrice ?? null,
        enabled: item.enabled,
      }
      : null,
  });
}

export async function DELETE(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return jsonWithBigInt({ error: "id is required" }, { status: 400 });
  }
  await connectMongo();
  await WatchlistItemModel.findByIdAndDelete(id);
  return jsonWithBigInt({ ok: true });
}
