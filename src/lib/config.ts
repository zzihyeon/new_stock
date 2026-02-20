import { env } from "@/lib/env";

export const config = {
  app: {
    env: env.NODE_ENV,
  },
  db: {
    uri: env.MONGODB_URI,
    dbName: env.MONGODB_DB_NAME,
  },
  kis: {
    baseUrl: env.KIS_BASE_URL,
    appKey: env.KIS_APP_KEY,
    appSecret: env.KIS_APP_SECRET,
    accountNo: env.KIS_ACCOUNT_NO,
    productCode: env.KIS_PRODUCT_CODE,
    accessToken: env.KIS_ACCESS_TOKEN,
    accessTokenExpiresAt: env.KIS_ACCESS_TOKEN_EXPIRES_AT,
  },
  telegram: {
    botToken: env.TELEGRAM_BOT_TOKEN,
    chatId: env.TELEGRAM_CHAT_ID,
  },
  jobs: {
    ingestApiKey: env.INGEST_API_KEY,
  },
} as const;

export function isKisConfigured(): boolean {
  return Boolean(config.kis.appKey && config.kis.appSecret);
}

export function isTelegramConfigured(): boolean {
  return Boolean(config.telegram.botToken && config.telegram.chatId);
}
