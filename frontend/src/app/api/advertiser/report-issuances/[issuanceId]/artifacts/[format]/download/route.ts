import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "../../../../_responses";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ issuanceId: string; format: string }> },
) {
  const { issuanceId, format } = await context.params;
  if (format !== "csv" && format !== "pdf") {
    return Response.json(
      {
        error: {
          code: "REPORT_ARTIFACT_FORMAT_INVALID",
          message: "The report artifact format is not supported",
          details: {},
        },
      },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST(
      "/api/v1/advertiser/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
      {
        params: { path: { issuance_id: issuanceId, artifact_format: format } },
        body: { reason: "Download the approved campaign performance artifact" },
      },
    );
    if (!data) throw new Error("Backend returned an empty report download");
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
