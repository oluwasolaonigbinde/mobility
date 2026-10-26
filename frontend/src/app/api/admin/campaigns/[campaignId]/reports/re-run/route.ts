import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "@/app/api/advertiser/report-issuances/_responses";
import type { components } from "@/lib/api/schema";

export async function POST(request: Request, context: { params: Promise<{ campaignId: string }> }) {
  try {
    const { campaignId } = await context.params;
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
    return reportIssuanceError(error);
  }
}
