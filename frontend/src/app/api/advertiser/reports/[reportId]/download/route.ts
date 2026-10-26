import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "../../../report-issuances/_responses";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ reportId: string }> }) {
  const { reportId } = await context.params;
  const query = new URL(request.url).searchParams;
  const format = query.get("format");
  if (format !== "csv" && format !== "pdf")
    return Response.json(
      {
        error: {
          code: "REPORT_FORMAT_INVALID",
          message: "Choose CSV or PDF",
          details: {},
        },
      },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  try {
    const api = createApiClient(await getSessionToken());
    const { data } =
      query.get("legacy") === "true"
        ? await api.POST(
            "/api/v1/advertiser/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
            {
              params: { path: { issuance_id: reportId, artifact_format: format } },
              body: { reason: "Download an issued campaign report" },
            },
          )
        : await api.POST(
            "/api/v1/advertiser/reports/{report_id}/artifacts/{artifact_format}/download",
            {
              params: { path: { report_id: reportId, artifact_format: format } },
              body: { reason: "Download a campaign report" },
            },
          );
    if (!data) throw new Error("Report download unavailable");
    return new Response(null, {
      status: 303,
      headers: {
        location: data.url,
        "cache-control": "no-store",
        "x-content-sha256": data.checksum_sha256,
      },
    });
  } catch (error) {
    return reportIssuanceError(error);
  }
}
