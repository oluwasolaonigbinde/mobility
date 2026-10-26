export function isPublicScanPath(value: unknown): boolean {
  if (typeof value !== "string") return false;
  try {
    return new URL(value, "https://cardvert.invalid").pathname.startsWith("/q/");
  } catch {
    return false;
  }
}

export function isScanEvent(event: { request?: { url?: string }; transaction?: string }): boolean {
  return isPublicScanPath(event.request?.url) || Boolean(event.transaction?.includes("/q/"));
}
