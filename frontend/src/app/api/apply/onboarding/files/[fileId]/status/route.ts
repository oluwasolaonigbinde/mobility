import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ fileId: string }> }) {
  const body = await request.json();
  const { fileId } = await context.params;
  return bffResponse((api) =>
    api.POST("/api/v1/auth/driver-onboarding/files/{file_id}/status", {
      params: { path: { file_id: fileId } },
      body: body as never,
    }),
  );
}
