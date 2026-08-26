import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ uploadId: string }> }) {
  const { uploadId } = await context.params;
  return bffResponse((api) =>
    api.POST("/api/v1/driver/files/uploads/{upload_id}/confirm", {
      params: { path: { upload_id: uploadId } },
    }),
  );
}
