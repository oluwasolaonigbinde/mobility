import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
  return bffResponse((api) =>
    api.GET("/api/v1/driver/files/{file_id}", {
      params: { path: { file_id: fileId } },
    }),
  );
}
