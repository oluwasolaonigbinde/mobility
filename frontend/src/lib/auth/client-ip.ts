/**
 * Return the edge-created client IP only when the deployment explicitly opts
 * into the private trusted-edge topology. FastAPI performs the authoritative
 * IP validation and verifies that the direct BFF peer is allowlisted.
 */
export function loginClientIpHeader(
  requestHeaders: Pick<Headers, "get">,
  relayEnabled: boolean,
): string | undefined {
  if (!relayEnabled) return undefined;
  return requestHeaders.get("x-client-ip") || undefined;
}
