import { NextResponse, type NextRequest } from "next/server";

function deny(status: number, code: string, message: string) {
  return NextResponse.json(
    { error: { code, message, details: {} } },
    {
      status,
      headers: { "cache-control": "no-store" },
    },
  );
}

export async function mutationBoundary(request: NextRequest): Promise<NextResponse | undefined> {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return;
  const configured =
    process.env.PUBLIC_ORIGIN ||
    (process.env.NODE_ENV === "production" ? "" : "http://localhost:3000");
  let origin: URL;
  try {
    origin = new URL(configured);
    if (!["http:", "https:"].includes(origin.protocol) || origin.origin !== configured)
      throw new Error("Invalid origin");
  } catch {
    return deny(503, "BFF_ORIGIN_UNAVAILABLE", "The browser request boundary is unavailable");
  }
  const path = request.nextUrl.pathname;
  const site = request.headers.get("sec-fetch-site");
  const mode = request.headers.get("sec-fetch-mode");
  const destination = request.headers.get("sec-fetch-dest");
  if (
    request.headers.get("origin") !== origin.origin ||
    (site !== null && site !== "same-origin") ||
    (mode !== null && !["cors", "same-origin"].includes(mode)) ||
    (destination !== null && destination !== "empty")
  )
    return deny(403, "BFF_ORIGIN_DENIED", "The browser request origin is not permitted");

  const bodyless =
    request.method === "POST" &&
    [
      /^\/api\/notifications\/read-all\/?$/,
      /^\/api\/notifications\/[^/]+\/read\/?$/,
      /^\/api\/(advertiser|driver)\/files\/uploads\/[^/]+\/confirm\/?$/,
      /^\/api\/admin\/files\/[^/]+\/installation-review\/?$/,
    ].some((pattern) => pattern.test(path));
  const mediaType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (bodyless) {
    // Next supplies a stream even for an empty POST. Inspect bytes, not stream presence.
    if (request.body) {
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
        reader = request.body.getReader();
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          if (chunk.value.byteLength) {
            return deny(
              415,
              "BFF_MEDIA_TYPE_DENIED",
              "Please retry this action without sending extra data",
            );
          }
        }
      } catch {
        return deny(400, "BFF_BODY_UNREADABLE", "The request body could not be read");
      } finally {
        reader?.releaseLock();
      }
    }
  } else if (mediaType !== "application/json") {
    return deny(415, "BFF_MEDIA_TYPE_DENIED", "This command requires application/json");
  }
}
