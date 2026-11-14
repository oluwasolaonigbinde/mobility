import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";
import { fileResponse } from "../../../_proxy";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ uploadId: string }> }) {
  const { uploadId } = await context.params;
  if (!isUuidParam(uploadId)) return unknownIdResponse();
  return fileResponse((api) =>
    api.POST("/api/v1/advertiser/files/uploads/{upload_id}/confirm", {
      params: { path: { upload_id: uploadId } },
    }),
  );
}
