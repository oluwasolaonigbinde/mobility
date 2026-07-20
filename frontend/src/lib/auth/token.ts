export interface TokenTiming {
  exp?: number;
}

export function tokenTiming(token: string): TokenTiming | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const normalized = part.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized)) as unknown;
    if (typeof decoded !== "object" || decoded === null) return null;
    const exp = (decoded as { exp?: unknown }).exp;
    return typeof exp === "number" ? { exp } : {};
  } catch {
    return null;
  }
}

export function tokenNeedsRefresh(
  token: string,
  thresholdSeconds: number,
  nowSeconds = Math.floor(Date.now() / 1000),
): boolean {
  const timing = tokenTiming(token);
  return typeof timing?.exp === "number" && timing.exp - nowSeconds < thresholdSeconds;
}
