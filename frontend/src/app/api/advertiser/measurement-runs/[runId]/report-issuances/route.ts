import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { reportIssuanceError } from "../../../report-issuances/_responses";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ runId: string }> }) {
  const { runId } = await context.params;
  try {
    const body = (await request.json()) as {
      client_request_id: string;
      reissue_of_id?: string | null;
    };
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST(
      "/api/v1/advertiser/measurement-runs/{run_id}/report-issuances",
      {
        params: { path: { run_id: runId } },
        body: {
          client_request_id: body.client_request_id,
          reissue_of_id: body.reissue_of_id ?? null,
        },
      },
    );
    if (!data) throw new Error("Backend returned an empty report issuance");
    return Response.json(data, {
      status: 202,
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    return reportIssuanceError(error);
  }
}
