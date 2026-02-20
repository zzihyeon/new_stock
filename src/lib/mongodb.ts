import mongoose from "mongoose";

import { config } from "@/lib/config";

declare global {
  // eslint-disable-next-line no-var
  var mongooseConn:
    | {
      conn: typeof mongoose | null;
      promise: Promise<typeof mongoose> | null;
    }
    | undefined;
}

const cached = global.mongooseConn ?? { conn: null, promise: null };
global.mongooseConn = cached;

export async function connectMongo() {
  if (cached.conn) {
    return cached.conn;
  }

  if (!config.db.uri) {
    throw new Error("MONGODB_URI is required.");
  }

  if (!cached.promise) {
    cached.promise = mongoose.connect(config.db.uri, {
      dbName: config.db.dbName,
      autoIndex: true,
      serverSelectionTimeoutMS: 5000,
    });
  }

  cached.conn = await cached.promise;
  return cached.conn;
}
