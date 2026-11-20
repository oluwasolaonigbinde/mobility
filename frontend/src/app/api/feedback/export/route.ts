import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
const PRIVATE_HEADERS = {
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
};

/** CSV export of every feedback note. */
export async function GET() {
  try {
    const { data } = await createApiClient().GET("/api/v1/feedback/export.csv", {
      parseAs: "arrayBuffer",
    });
    return new Response(data ?? new ArrayBuffer(0), {
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": 'attachment; filename="cardvert-feedback.csv"',
        ...PRIVATE_HEADERS,
      },
    });
  } catch (error) {
    return new Response(null, {
      headers: PRIVATE_HEADERS,
      status: error instanceof ApiError && error.status === 404 ? 404 : 503,
    });
  }
}
