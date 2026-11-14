const SENSITIVE_KEY =
  /^(request|user)$|authorization|cookie|password|secret|token|bank|iban|account_number|latitude|longitude|gps|fraud|evidence|artifact|private_url|signed_url/i;
const PRIVATE_URL = /https?:\/\/[^\s"']+/gi;
const BEARER_OR_JWT = /(?:bearer\s+)?eyJ[A-Za-z0-9._-]+/gi;
const PRECISE_COORDINATE = /\b(?:lat(?:itude)?|lon(?:gitude)?|gps)\s*[=:]\s*-?\d+(?:\.\d+)?/gi;
// Relative URLs in navigation breadcrumbs keep query and fragment, e.g. an Apply link's token.
const URL_TOKEN = /([?#&][\w-]*token=)[^&#\s"']*/gi;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/g;
// International numbers need a leading "+"; local ones are Nigerian mobile numbers (070-091...).
const INTERNATIONAL_PHONE = /\+\d(?:[\s().-]{0,2}\d){8,14}/g;
const LOCAL_PHONE = /\b0[789][01]\d(?:[\s-]?\d){7}\b/g;

function scrub(value: unknown): unknown {
  if (typeof value === "string") {
    return value
      .replace(PRIVATE_URL, "[REDACTED_URL]")
      .replace(URL_TOKEN, "$1[REDACTED_TOKEN]")
      .replace(EMAIL, "[REDACTED_EMAIL]")
      .replace(INTERNATIONAL_PHONE, "[REDACTED_PHONE]")
      .replace(LOCAL_PHONE, "[REDACTED_PHONE]")
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
