import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";
import { fileResponse } from "../_proxy";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
  if (!isUuidParam(fileId)) return unknownIdResponse();
  return fileResponse((api) =>
    api.GET("/api/v1/advertiser/files/{file_id}", {
      params: { path: { file_id: fileId } },
    }),
  );
}
