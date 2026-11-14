import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ uploadId: string }> }) {
  const { uploadId } = await context.params;
  if (!isUuidParam(uploadId)) return unknownIdResponse();
  return bffResponse((api) =>
    api.POST("/api/v1/driver/files/uploads/{upload_id}/confirm", {
      params: { path: { upload_id: uploadId } },
    }),
  );
}
