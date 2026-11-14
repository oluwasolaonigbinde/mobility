import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
  if (!isUuidParam(fileId)) return unknownIdResponse();
  return bffResponse((api) =>
    api.POST("/api/v1/admin/files/{file_id}/download", {
      params: { path: { file_id: fileId } },
      body: {
        purpose: "installation_review",
        reason: "Review assignment installation evidence",
      },
    }),
  );
}
