import { InferSchemaType, Model, Schema, model, models } from "mongoose";

export type Timeframe = "DAY" | "MINUTE";

const stockSchema = new Schema(
  {
    symbol: { type: String, required: true, unique: true, uppercase: true, index: true },
    name: { type: String, required: true },
    market: { type: String, required: true },
  },
  { timestamps: true },
);

const candleSchema = new Schema(
  {
    symbol: { type: String, required: true, uppercase: true, index: true },
    timeframe: { type: String, enum: ["DAY", "MINUTE"], required: true, index: true },
    baseDate: { type: String, required: true, index: true },
    baseTime: { type: String, required: true, index: true },
    open: { type: Number, required: true },
    high: { type: Number, required: true },
    low: { type: Number, required: true },
    close: { type: Number, required: true },
    volume: { type: Number, required: true },
    tradeValue: { type: Number, required: false },
  },
  { timestamps: true },
);

candleSchema.index({ symbol: 1, timeframe: 1, baseDate: 1, baseTime: 1 }, { unique: true });

const watchlistItemSchema = new Schema(
  {
    symbol: { type: String, required: true, uppercase: true, index: true },
    memo: { type: String },
    targetPrice: { type: Number },
    stopPrice: { type: Number },
    enabled: { type: Boolean, default: true },
  },
  { timestamps: true },
);

const backtestRunSchema = new Schema(
  {
    symbol: { type: String, required: true, uppercase: true, index: true },
    timeframe: { type: String, enum: ["DAY", "MINUTE"], required: true },
    fromDate: { type: String, required: true },
    toDate: { type: String, required: true },
    ruleName: { type: String, required: true },
    initialCapital: { type: Number, required: true },
    finalCapital: { type: Number, required: true },
    totalReturnPct: { type: Number, required: true },
    maxDrawdownPct: { type: Number, required: true },
    trades: { type: Number, required: true },
    summary: { type: Schema.Types.Mixed },
  },
  { timestamps: true },
);

export type StockDoc = InferSchemaType<typeof stockSchema>;
export type CandleDoc = InferSchemaType<typeof candleSchema>;
export type WatchlistItemDoc = InferSchemaType<typeof watchlistItemSchema>;
export type BacktestRunDoc = InferSchemaType<typeof backtestRunSchema>;

function getOrCreateModel<T>(name: string, schema: Schema): Model<T> {
  return (models[name] as Model<T>) || model<T>(name, schema);
}

export const StockModel = getOrCreateModel<StockDoc>("Stock", stockSchema);
export const CandleModel = getOrCreateModel<CandleDoc>("Candle", candleSchema);
export const WatchlistItemModel = getOrCreateModel<WatchlistItemDoc>(
  "WatchlistItem",
  watchlistItemSchema,
);
export const BacktestRunModel = getOrCreateModel<BacktestRunDoc>("BacktestRun", backtestRunSchema);
