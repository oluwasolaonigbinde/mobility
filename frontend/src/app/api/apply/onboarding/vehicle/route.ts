import { bffResponse } from "@/lib/api/route-response";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  return bffResponse((api) =>
    api.POST("/api/v1/auth/driver-onboarding/vehicle", { body: body as never }),
  );
}
