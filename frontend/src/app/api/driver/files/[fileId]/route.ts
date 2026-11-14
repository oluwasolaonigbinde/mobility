import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
  if (!isUuidParam(fileId)) return unknownIdResponse();
  return bffResponse((api) =>
    api.GET("/api/v1/driver/files/{file_id}", {
      params: { path: { file_id: fileId } },
    }),
  );
}
