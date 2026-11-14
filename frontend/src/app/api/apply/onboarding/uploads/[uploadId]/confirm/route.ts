import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ uploadId: string }> }) {
  const { uploadId } = await context.params;
  if (!isUuidParam(uploadId)) return unknownIdResponse();
  const body = await request.json();
  return bffResponse((api) =>
    api.POST("/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm", {
      params: { path: { upload_id: uploadId } },
      body: body as never,
    }),
  );
}
