import { z } from "zod";

/**
 * Dynamic BFF path ids are backend UUIDs. Anything else, including a decoded slash,
 * is refused before a backend call so a segment can never retarget another route.
 */
export function isUuidParam(...values: string[]): boolean {
  return values.every((value) => z.uuid().safeParse(value).success);
}

/** A backend-signed storage URL is only followed or redirected to as plain http(s) without credentials. */
export function storageUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function unknownIdResponse(): Response {
  return Response.json(
    { error: { code: "NOT_FOUND", message: "That item was not found.", details: {} } },
    { status: 404, headers: { "cache-control": "no-store" } },
  );
}
