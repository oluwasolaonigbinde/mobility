import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(request: Request, context: { params: Promise<{ uploadId: string }> }) {
  const body = await request.json();
  const { uploadId } = await context.params;
  return bffResponse((api) =>
    api.POST("/api/v1/auth/driver-onboarding/files/uploads/{upload_id}/confirm", {
      params: { path: { upload_id: uploadId } },
      body: body as never,
    }),
  );
}
