import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { readDriverJobArtwork } from "@/lib/api/audit-batch2";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

const MAX_BYTES = 25 * 1024 * 1024;
const RASTERS = ["image/png", "image/jpeg", "image/webp"];
function unavailable(status: number) {
  return new Response(null, {
    status,
    headers: { "cache-control": "private, no-store", "x-content-type-options": "nosniff" },
  });
}
export const dynamic = "force-dynamic";
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ assignmentId: string }> },
) {
  const { assignmentId } = await params;
  if (!z.uuid().safeParse(assignmentId).success) return unavailable(404);
  const token = await getSessionToken();
  if (!token) return unavailable(401);
  try {
    const { data } = await readDriverJobArtwork(createApiClient(token), assignmentId);
    if (!data || !Number.isFinite(data.expires_in_seconds) || !(data.expires_in_seconds > 0))
      return unavailable(404);
    const url = new URL(data.url);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
      return unavailable(404);
    const upstream = await fetch(url.href, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    const mime = upstream.headers.get("content-type")?.split(";")[0];
    if (
      !upstream.ok ||
      !mime ||
      ![...RASTERS, "application/pdf", "video/mp4"].includes(mime) ||
      Number(upstream.headers.get("content-length")) > MAX_BYTES
    ) {
      await upstream.body?.cancel();
      return unavailable(404);
    }
    const reader = upstream.body?.getReader();
    if (!reader) return unavailable(404);
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_BYTES) {
        await reader.cancel();
        return unavailable(413);
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    return new Response(bytes, {
      headers: {
        "content-type": mime,
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'none'; sandbox",
        ...(RASTERS.includes(mime)
          ? {}
          : {
              "content-disposition": `attachment; filename="campaign-advert.${mime === "application/pdf" ? "pdf" : "mp4"}"`,
            }),
      },
    });
  } catch (error) {
    return unavailable(
      error instanceof ApiError && [401, 403, 404, 409].includes(error.status) ? error.status : 503,
    );
  }
}
