import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export const dynamic = "force-dynamic";
export async function GET(
  request: Request,
  { params }: { params: Promise<{ campaignId: string; creativeId: string }> },
) {
  const { campaignId, creativeId } = await params;
  const headers = {
    "cache-control": "private, no-store",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
  };
  if (!z.uuid().safeParse(campaignId).success || !z.uuid().safeParse(creativeId).success)
    return new Response(null, { status: 404, headers });
  const token = await getSessionToken();
  if (!token) return new Response(null, { status: 401, headers });
  try {
    const { data } = await createApiClient(token).GET(
      "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/qr.svg",
      {
        params: { path: { campaign_id: campaignId, creative_id: creativeId } },
        parseAs: "arrayBuffer",
      },
    );
    if (!data || data.byteLength > 200_000) return new Response(null, { status: 503, headers });
    return new Response(data, {
      headers: {
        ...headers,
        "content-type": "image/svg+xml",
        "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "content-disposition": `${new URL(request.url).searchParams.has("download") ? "attachment" : "inline"}; filename="advert-qr.svg"`,
      },
    });
  } catch (error) {
    return new Response(null, {
      status:
        error instanceof ApiError && [401, 403, 404, 409].includes(error.status)
          ? error.status
          : 503,
      headers,
    });
  }
}
