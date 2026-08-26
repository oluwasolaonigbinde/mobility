import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, context: { params: Promise<{ fileId: string }> }) {
  const { fileId } = await context.params;
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
