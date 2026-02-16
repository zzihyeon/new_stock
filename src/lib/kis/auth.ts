import { config } from "@/lib/config";

type KISTokenResponse = {
  access_token: string;
  expires_in: number;
  token_type: string;
};

let cachedToken: { value: string; expiresAt: number } | null = null;

function getPresetToken() {
  if (!config.kis.accessToken) {
    return null;
  }
  const expiryFromEnv = config.kis.accessTokenExpiresAt
    ? Number(new Date(config.kis.accessTokenExpiresAt))
    : Number.POSITIVE_INFINITY;
  return {
    value: config.kis.accessToken,
    expiresAt: expiryFromEnv,
  };
}

export async function getKisAccessToken(forceRefresh = false): Promise<string> {
  if (!config.kis.appKey || !config.kis.appSecret) {
    throw new Error("KIS_APP_KEY and KIS_APP_SECRET are required.");
  }

  const now = Date.now();

  if (!forceRefresh && cachedToken && cachedToken.expiresAt > now + 60_000) {
    return cachedToken.value;
  }

  if (!forceRefresh) {
    const presetToken = getPresetToken();
    if (presetToken && presetToken.expiresAt > now + 60_000) {
      cachedToken = presetToken;
      return presetToken.value;
    }
  }

  const response = await fetch(`${config.kis.baseUrl}/oauth2/tokenP`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      grant_type: "client_credentials",
      appkey: config.kis.appKey,
      appsecret: config.kis.appSecret,
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`KIS token request failed: ${response.status} ${body}`);
  }

  const payload = (await response.json()) as KISTokenResponse;
  cachedToken = {
    value: payload.access_token,
    expiresAt: Date.now() + payload.expires_in * 1000,
  };
  return payload.access_token;
}
