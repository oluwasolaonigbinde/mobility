import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { isUuidParam, storageUrl } from "@/lib/api/route-params";
import { getSessionToken } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await params;
  if (!isUuidParam(fileId)) return new Response(null, { status: 404 });
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
    const location = data ? storageUrl(data.url) : null;
    if (!location) return new Response(null, { status: 404 });
    return new Response(null, {
      status: 303,
      headers: { location, "cache-control": "private, no-store" },
    });
  } catch (error) {
    return new Response(null, {
      status: error instanceof ApiError ? error.status : 503,
      headers: { "cache-control": "private, no-store" },
    });
  }
}
