import { z } from "zod";

const envSchema = z.object({
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .optional()
    .default("development"),
  DATABASE_URL: z.string().optional().default(""),
  KIS_BASE_URL: z.string().url().default("https://openapi.koreainvestment.com:9443"),
  KIS_APP_KEY: z.string().optional().default(""),
  KIS_APP_SECRET: z.string().optional().default(""),
  KIS_ACCOUNT_NO: z.string().optional().default(""),
  KIS_PRODUCT_CODE: z.string().min(2).default("01"),
  KIS_ACCESS_TOKEN: z.string().optional(),
  KIS_ACCESS_TOKEN_EXPIRES_AT: z.string().optional(),
  INGEST_API_KEY: z.string().optional(),
  TELEGRAM_BOT_TOKEN: z.string().optional().default(""),
  TELEGRAM_CHAT_ID: z.string().optional().default(""),
});

export const env = envSchema.parse(process.env);
