import { bffResponse } from "@/lib/api/route-response";
export async function POST() {
  return bffResponse((api) => api.POST("/api/v1/driver/contact/phone-verification"));
}
