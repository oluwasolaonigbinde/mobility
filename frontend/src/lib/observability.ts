const SENSITIVE_KEY =
  /^(request|user)$|authorization|cookie|password|secret|token|bank|iban|account_number|latitude|longitude|gps|fraud|evidence|artifact|private_url|signed_url/i;
const PRIVATE_URL = /https?:\/\/[^\s"']+/gi;
const BEARER_OR_JWT = /(?:bearer\s+)?eyJ[A-Za-z0-9._-]+/gi;
const PRECISE_COORDINATE = /\b(?:lat(?:itude)?|lon(?:gitude)?|gps)\s*[=:]\s*-?\d+(?:\.\d+)?/gi;

function scrub(value: unknown): unknown {
  if (typeof value === "string") {
    return value
      .replace(PRIVATE_URL, "[REDACTED_URL]")
      .replace(BEARER_OR_JWT, "[REDACTED_TOKEN]")
      .replace(PRECISE_COORDINATE, "[REDACTED_GPS]");
  }
  if (Array.isArray(value)) {
    return value.map(scrub);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !SENSITIVE_KEY.test(key))
        .map(([key, item]) => [key, scrub(item)]),
    );
  }
  return value;
}

export function scrubSentryEvent<T>(event: T): T {
  return scrub(event) as T;
}
