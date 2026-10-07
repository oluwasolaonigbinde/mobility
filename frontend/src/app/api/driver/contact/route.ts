import { bffResponse } from "@/lib/api/route-response";
export const dynamic = "force-dynamic";
export async function GET() {
  return bffResponse((api) => api.GET("/api/v1/driver/contact"));
}
