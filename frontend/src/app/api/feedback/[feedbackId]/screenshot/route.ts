import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { isUuidParam } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";
const PRIVATE_HEADERS = {
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
};

/** Feedback screenshot for the review page. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ feedbackId: string }> },
) {
  const { feedbackId } = await params;
  if (!isUuidParam(feedbackId))
    return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
  try {
    const { data } = await createApiClient().GET("/api/v1/feedback/{feedback_id}/screenshot", {
      params: { path: { feedback_id: feedbackId } },
      parseAs: "arrayBuffer",
    });
    if (!data) return new Response(null, { status: 404, headers: PRIVATE_HEADERS });
    return new Response(data, { headers: { "content-type": "image/jpeg", ...PRIVATE_HEADERS } });
  } catch (error) {
    return new Response(null, {
      headers: PRIVATE_HEADERS,
      status: error instanceof ApiError && error.status === 404 ? 404 : 503,
    });
  }
}
