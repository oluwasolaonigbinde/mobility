import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "@/app/api/advertiser/report-issuances/_responses";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";
import type { components } from "@/lib/api/schema";

/** Refusal codes the re-run endpoint returns (report_scheduling.py). */
const RERUN_REFUSALS = {
  REPORT_NOT_DUE: "A new report can't be prepared yet.",
  CAMPAIGN_NOT_FOUND: "This campaign couldn't be found. Refresh the page.",
  REPORT_REQUEST_CONFLICT: "This request was already used. Refresh the page and try again.",
};

export async function POST(request: Request, context: { params: Promise<{ campaignId: string }> }) {
  const { campaignId } = await context.params;
  if (!isUuidParam(campaignId)) return unknownIdResponse();
  try {
    const body = (await request.json()) as components["schemas"]["CampaignReportRerun"];
    const { data } = await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/campaigns/{campaign_id}/reports/re-run",
      {
        params: { path: { campaign_id: campaignId } },
        body,
      },
    );
    return Response.json(data, { status: 202, headers: { "cache-control": "no-store" } });
  } catch (error) {
    return reportIssuanceError(error, RERUN_REFUSALS);
  }
}
