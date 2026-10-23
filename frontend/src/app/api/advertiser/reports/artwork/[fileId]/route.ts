import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await params;
  if (!z.string().uuid().safeParse(fileId).success) return new Response(null, { status: 404 });
  const token = await getSessionToken();
  if (!token) return new Response(null, { status: 401 });
  try {
    const { data } = await createApiClient(token).POST(
      "/api/v1/advertiser/files/{file_id}/download",
      {
        params: { path: { file_id: fileId } },
        body: { purpose: "campaign_preview", reason: "Report artwork preview" },
      },
    );
    if (!data) return new Response(null, { status: 404 });
    return new Response(null, {
      status: 303,
      headers: { location: data.url, "cache-control": "private, no-store" },
    });
  } catch (error) {
    return new Response(null, {
      status: error instanceof ApiError ? error.status : 503,
      headers: { "cache-control": "private, no-store" },
    });
  }
}
