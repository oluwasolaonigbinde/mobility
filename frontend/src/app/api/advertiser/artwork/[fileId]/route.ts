import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

const MAX_BYTES = 25 * 1024 * 1024;
const PRIVATE_HEADERS = {
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
};
export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await params;
  if (!z.string().uuid().safeParse(fileId).success)
    return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
  const token = await getSessionToken();
  if (!token) return new Response(null, { status: 401, headers: PRIVATE_HEADERS });
  try {
    const api = createApiClient(token);
    const { data } = await api.POST("/api/v1/advertiser/files/{file_id}/download", {
      params: { path: { file_id: fileId } },
      body: { purpose: "campaign_preview", reason: "Campaign artwork preview" },
    });
    if (!data) return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
    const upstream = await fetch(data.url, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    const contentType = upstream.headers.get("content-type")?.split(";")[0];
    if (
      !upstream.ok ||
      !contentType ||
      !["image/png", "image/jpeg", "image/webp", "application/pdf"].includes(contentType) ||
      Number(upstream.headers.get("content-length")) > MAX_BYTES
    ) {
      await upstream.body?.cancel();
      return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
    }
    const reader = upstream.body?.getReader();
    if (!reader) return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_BYTES) {
        await reader.cancel();
        return new Response(null, { status: 413, headers: PRIVATE_HEADERS });
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
        "content-type": contentType,
        ...PRIVATE_HEADERS,
        ...(contentType === "application/pdf"
          ? {
              "content-disposition": 'inline; filename="artwork.pdf"',
              "content-security-policy": "default-src 'none'; sandbox",
            }
          : {}),
      },
    });
  } catch (error) {
    return new Response(null, {
      headers: PRIVATE_HEADERS,
      status:
        error instanceof ApiError && [401, 403, 404].includes(error.status) ? error.status : 503,
    });
  }
}
