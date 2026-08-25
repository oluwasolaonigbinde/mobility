import { notificationResponse } from "./_proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return notificationResponse((api) => api.GET("/api/v1/notifications"));
}
