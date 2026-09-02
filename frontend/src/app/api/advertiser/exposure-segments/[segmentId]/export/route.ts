import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ segmentId: string }> }) {
  const { segmentId } = await context.params;
  try {
    const form = await request.formData();
    const approvalId = form.get("approval_id");
    if (typeof approvalId !== "string" || approvalId.length === 0) {
      return Response.json(
        {
          error: {
            code: "AUDIENCE_DELIVERY_APPROVAL_REQUIRED",
            message: "A current aggregate-export approval is required",
            details: {},
          },
        },
        { status: 422, headers: { "cache-control": "no-store" } },
      );
    }
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/advertiser/exposure-segments/{segment_id}/exports", {
      params: {
        path: { segment_id: segmentId },
        header: { "Idempotency-Key": `w3-01d-export-${segmentId}` },
      },
      body: { approval_id: approvalId },
    });
    if (!data) throw new Error("Backend returned an empty export");
    return new Response(data.csv_content, {
      headers: {
        "cache-control": "no-store",
        "content-disposition": `attachment; filename="cardvert-targeting-${segmentId}.csv"`,
        "content-type": "text/csv; charset=utf-8",
        "x-content-sha256": data.csv_sha256,
      },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return Response.json(
        {
          error: {
            code: error.code,
            message: error.message,
            details: error.details ?? {},
            request_id: error.requestId,
          },
        },
        { status: error.status, headers: { "cache-control": "no-store" } },
      );
    }
    return Response.json(
      {
        error: {
          code: "INTERNAL_SERVER_ERROR",
          message: "The aggregate export could not be completed",
          details: {},
        },
      },
      { status: 500, headers: { "cache-control": "no-store" } },
    );
  }
}
