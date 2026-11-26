import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "../report-issuances/_responses";
import type { components } from "@/lib/api/schema";

/** Refusal codes the create endpoint returns (campaign_reports.py). */
const CREATE_REFUSALS = {
  REPORT_NO_CAMPAIGNS: "There are no campaigns to report on.",
  REPORT_TOO_LARGE: "Choose fewer campaigns or a shorter reporting period.",
  REPORT_REQUEST_CONFLICT: "This request was already used. Refresh the page and try again.",
};

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const query = new URL(request.url).searchParams;
    const { data } = await createApiClient(await getSessionToken()).GET(
      "/api/v1/advertiser/reports",
      {
        params: {
          query: {
            campaign_id: query.get("campaign_id") || undefined,
            limit: 25,
            offset: Number(query.get("offset") || 0),
          },
        },
      },
    );
    return Response.json(data, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    return reportIssuanceError(error);
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as components["schemas"]["CampaignReportCreate"];
    const { data } = await createApiClient(await getSessionToken()).POST(
      "/api/v1/advertiser/reports",
      { body },
    );
    return Response.json(data, { status: 202, headers: { "cache-control": "no-store" } });
  } catch (error) {
    return reportIssuanceError(error, CREATE_REFUSALS);
  }
}
