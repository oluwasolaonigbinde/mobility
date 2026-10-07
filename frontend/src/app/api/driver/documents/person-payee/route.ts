import { bffResponse } from "@/lib/api/route-response";
export async function POST(request: Request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { error: { code: "INVALID_REQUEST", message: "Check the form and try again." } },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  return bffResponse((api) => api.POST("/api/v1/driver/documents/person-payee", { body }));
}
