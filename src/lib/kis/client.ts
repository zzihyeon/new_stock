import { config } from "@/lib/config";
import { getKisAccessToken } from "@/lib/kis/auth";

export type CandleInput = {
  symbol: string;
  baseDate: string;
  baseTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: bigint;
  tradeValue?: bigint;
};

export type QuoteSnapshot = {
  symbol: string;
  price: number;
  prevClose: number;
  volume: number;
  changeRate: number;
};

type KISResponse<T> = {
  rt_cd: string;
  msg_cd: string;
  msg1: string;
  output?: T;
  output1?: T;
  output2?: T;
};

function toNumber(value: string | number | null | undefined): number {
  if (value == null || value === "") {
    return 0;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function toBigInt(value: string | number | null | undefined): bigint {
  if (value == null || value === "") {
    return BigInt(0);
  }
  return BigInt(String(value));
}

async function kisGet<T>(
  path: string,
  trId: string,
  searchParams: Record<string, string>,
): Promise<KISResponse<T>> {
  const token = await getKisAccessToken();
  const url = new URL(`${config.kis.baseUrl}${path}`);
  Object.entries(searchParams).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: {
      "content-type": "application/json; charset=utf-8",
      authorization: `Bearer ${token}`,
      appkey: config.kis.appKey,
      appsecret: config.kis.appSecret,
      tr_id: trId,
      custtype: "P",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`KIS request failed: ${response.status} ${body}`);
  }

  return (await response.json()) as KISResponse<T>;
}

export async function fetchDailyCandles(
  symbol: string,
  periodCode: "D" | "W" | "M" = "D",
): Promise<CandleInput[]> {
  const result = await kisGet<Array<Record<string, string>>>(
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
    "FHKST03010100",
    {
      FID_COND_MRKT_DIV_CODE: "J",
      FID_INPUT_ISCD: symbol,
      FID_PERIOD_DIV_CODE: periodCode,
      FID_ORG_ADJ_PRC: "0",
    },
  );

  const rows = result.output2 ?? result.output1 ?? [];
  return rows.map((row) => ({
    symbol,
    baseDate: row.stck_bsop_date ?? "",
    baseTime: "000000",
    open: toNumber(row.stck_oprc),
    high: toNumber(row.stck_hgpr),
    low: toNumber(row.stck_lwpr),
    close: toNumber(row.stck_clpr),
    volume: toBigInt(row.acml_vol),
    tradeValue: toBigInt(row.acml_tr_pbmn),
  }));
}

export async function fetchMinuteCandles(symbol: string): Promise<CandleInput[]> {
  const now = new Date();
  const hm = `${String(now.getHours()).padStart(2, "0")}${String(
    now.getMinutes(),
  ).padStart(2, "0")}00`;

  const result = await kisGet<Array<Record<string, string>>>(
    "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
    "FHKST03010200",
    {
      FID_ETC_CLS_CODE: "",
      FID_COND_MRKT_DIV_CODE: "J",
      FID_INPUT_ISCD: symbol,
      FID_INPUT_HOUR_1: hm,
      FID_PW_DATA_INCU_YN: "Y",
    },
  );

  const rows = result.output2 ?? result.output1 ?? [];
  return rows.map((row) => ({
    symbol,
    baseDate: row.stck_bsop_date ?? "",
    baseTime: row.stck_cntg_hour ?? "000000",
    open: toNumber(row.stck_oprc),
    high: toNumber(row.stck_hgpr),
    low: toNumber(row.stck_lwpr),
    close: toNumber(row.stck_prpr),
    volume: toBigInt(row.cntg_vol),
    tradeValue: toBigInt(row.acml_tr_pbmn),
  }));
}

export async function fetchQuoteSnapshot(symbol: string): Promise<QuoteSnapshot> {
  const result = await kisGet<Record<string, string>>(
    "/uapi/domestic-stock/v1/quotations/inquire-price",
    "FHKST01010100",
    {
      FID_COND_MRKT_DIV_CODE: "J",
      FID_INPUT_ISCD: symbol,
    },
  );

  const row = result.output ?? {};
  return {
    symbol,
    price: toNumber(row.stck_prpr),
    prevClose: toNumber(row.stck_sdpr),
    volume: toNumber(row.acml_vol),
    changeRate: toNumber(row.prdy_ctrt),
  };
}
