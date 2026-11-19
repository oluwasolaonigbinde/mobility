import { getReviewToken } from "@/app/feedback/review-cookie";
import { createFeedbackReviewApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
const PRIVATE_HEADERS = {
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
};
const backToGate = () =>
  new Response(null, { status: 303, headers: { location: "/feedback", ...PRIVATE_HEADERS } });

/** CSV export of every feedback note; the review token stays in a header. */
export async function GET() {
  const token = await getReviewToken();
  if (!token) return backToGate();
  try {
    const { data } = await createFeedbackReviewApiClient(token).GET("/api/v1/feedback/export.csv", {
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
    if (error instanceof ApiError && error.status === 401) return backToGate();
    return new Response(null, {
      headers: PRIVATE_HEADERS,
      status: error instanceof ApiError && error.status === 404 ? 404 : 503,
    });
  }
}
