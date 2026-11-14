import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
  if (!isUuidParam(fileId)) return unknownIdResponse();
  const body = await request.json();
  return bffResponse((api) =>
    api.POST("/api/v1/auth/driver-onboarding/files/{file_id}/status", {
      params: { path: { file_id: fileId } },
      body: body as never,
    }),
  );
}
