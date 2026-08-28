import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "../_responses";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ issuanceId: string }> }) {
  const { issuanceId } = await context.params;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/advertiser/report-issuances/{issuance_id}", {
      params: { path: { issuance_id: issuanceId } },
    });
    if (!data) throw new Error("Backend returned an empty report issuance");
    return Response.json(data, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    return reportIssuanceError(error);
  }
}
