import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ assignmentId: string }> },
) {
  const { assignmentId } = await context.params;
  if (!isUuidParam(assignmentId)) return unknownIdResponse();
  const body = await request.json();
  return bffResponse((api) =>
    api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence", {
      params: { path: { assignment_id: assignmentId } },
      body: body as never,
    }),
  );
}
