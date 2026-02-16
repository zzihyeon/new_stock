import { NextRequest } from "next/server";

import { config } from "@/lib/config";
import { jsonWithBigInt } from "@/lib/http";
import { runDefaultIngestion } from "@/lib/ingest";

function isAuthorized(request: NextRequest): boolean {
  if (!config.jobs.ingestApiKey) {
    return true;
  }
  const auth = request.headers.get("x-api-key");
  return auth === config.jobs.ingestApiKey;
}

export async function POST(request: NextRequest) {
  if (!isAuthorized(request)) {
    return jsonWithBigInt({ error: "Unauthorized" }, { status: 401 });
  }

  const summaries = await runDefaultIngestion();
  return jsonWithBigInt({
    ok: true,
    symbols: summaries.length,
    summaries,
    ranAt: new Date().toISOString(),
  });
}
