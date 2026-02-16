export function jsonWithBigInt(data: unknown, init?: ResponseInit): Response {
  return new Response(
    JSON.stringify(data, (_, value) =>
      typeof value === "bigint" ? value.toString() : value,
    ),
    {
      ...init,
      headers: {
        "content-type": "application/json; charset=utf-8",
        ...(init?.headers ?? {}),
      },
    },
  );
}
