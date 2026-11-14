import { bffResponse } from "@/lib/api/route-response";
import { isUuidParam, unknownIdResponse } from "@/lib/api/route-params";
export async function POST(request: Request, context: { params: Promise<{ vehicleId: string }> }) {
  const { vehicleId } = await context.params;
  if (!isUuidParam(vehicleId)) return unknownIdResponse();
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { error: { code: "INVALID_REQUEST", message: "Check the form and try again." } },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  return bffResponse((api) =>
    api.POST("/api/v1/driver/vehicles/{vehicle_id}/evidence-submissions", {
      params: { path: { vehicle_id: vehicleId } },
      body,
    }),
  );
}
