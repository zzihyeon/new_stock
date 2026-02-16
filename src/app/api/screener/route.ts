import { NextRequest } from "next/server";
import { Prisma } from "@prisma/client";
import { z } from "zod";

import { prisma } from "@/lib/db";
import { jsonWithBigInt } from "@/lib/http";

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
  volume: bigint;
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
  const sql = Prisma.sql`
    WITH latest AS (
      SELECT c.symbol, MAX(c."baseDate") AS "baseDate"
      FROM "Candle" c
      WHERE c.timeframe = 'DAY'
      GROUP BY c.symbol
    )
    SELECT s.symbol, s.name, c.close, c.open, c.volume, c."baseDate" AS "baseDate",
      CASE WHEN c.open = 0 THEN 0
      ELSE ROUND(((c.close - c.open)::numeric / c.open::numeric) * 100, 2) END AS "changeRate"
    FROM latest l
    JOIN "Candle" c ON c.symbol = l.symbol AND c."baseDate" = l."baseDate" AND c.timeframe = 'DAY'
    JOIN "Stock" s ON s.symbol = c.symbol
    WHERE 1 = 1
    ${
      typeof filters.minPrice === "number"
        ? Prisma.sql`AND c.close >= ${filters.minPrice}`
        : Prisma.empty
    }
    ${
      typeof filters.maxPrice === "number"
        ? Prisma.sql`AND c.close <= ${filters.maxPrice}`
        : Prisma.empty
    }
    ${
      typeof filters.minVolume === "number"
        ? Prisma.sql`AND c.volume >= ${filters.minVolume}`
        : Prisma.empty
    }
    ${
      typeof filters.minChangeRate === "number"
        ? Prisma.sql`AND ((CASE WHEN c.open = 0 THEN 0 ELSE ((c.close - c.open)::numeric / c.open::numeric) * 100 END) >= ${filters.minChangeRate})`
        : Prisma.empty
    }
    ORDER BY c.volume DESC
    LIMIT 100
  `;

  const rows = await prisma.$queryRaw<ScreenerRow[]>(sql);
  return jsonWithBigInt({ count: rows.length, rows });
}
