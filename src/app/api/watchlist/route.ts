import { NextRequest } from "next/server";
import { z } from "zod";

import { prisma } from "@/lib/db";
import { jsonWithBigInt } from "@/lib/http";

const createSchema = z.object({
  symbol: z.string().min(6).max(12),
  memo: z.string().max(200).optional(),
  targetPrice: z.number().int().positive().optional(),
  stopPrice: z.number().int().positive().optional(),
});

const updateSchema = createSchema.partial().extend({
  id: z.coerce.bigint(),
  enabled: z.boolean().optional(),
});

export async function GET() {
  const items = await prisma.watchlistItem.findMany({
    orderBy: { createdAt: "desc" },
    include: { stock: true },
  });
  return jsonWithBigInt({ count: items.length, items });
}

export async function POST(request: NextRequest) {
  const payload = await request.json().catch(() => ({}));
  const parsed = createSchema.safeParse(payload);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  const symbol = parsed.data.symbol.toUpperCase();
  await prisma.stock.upsert({
    where: { symbol },
    update: {},
    create: { symbol, name: symbol, market: "KOSPI" },
  });

  const item = await prisma.watchlistItem.create({
    data: {
      symbol,
      memo: parsed.data.memo,
      targetPrice: parsed.data.targetPrice,
      stopPrice: parsed.data.stopPrice,
      enabled: true,
    },
  });

  return jsonWithBigInt({ item }, { status: 201 });
}

export async function PATCH(request: NextRequest) {
  const payload = await request.json().catch(() => ({}));
  const parsed = updateSchema.safeParse(payload);
  if (!parsed.success) {
    return jsonWithBigInt({ error: parsed.error.flatten() }, { status: 400 });
  }

  const item = await prisma.watchlistItem.update({
    where: { id: parsed.data.id },
    data: {
      symbol: parsed.data.symbol?.toUpperCase(),
      memo: parsed.data.memo,
      targetPrice: parsed.data.targetPrice,
      stopPrice: parsed.data.stopPrice,
      enabled: parsed.data.enabled,
    },
  });

  return jsonWithBigInt({ item });
}

export async function DELETE(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return jsonWithBigInt({ error: "id is required" }, { status: 400 });
  }
  await prisma.watchlistItem.delete({ where: { id: BigInt(id) } });
  return jsonWithBigInt({ ok: true });
}
