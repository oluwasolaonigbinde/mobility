import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ assignmentId: string }> },
) {
  const { assignmentId } = await context.params;
  const body = await request.json();
  return bffResponse((api) =>
    api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/display-proof", {
      params: { path: { assignment_id: assignmentId } },
      body: body as never,
    }),
  );
}
