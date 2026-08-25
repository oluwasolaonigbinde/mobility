import { notificationResponse } from "../_proxy";

export const dynamic = "force-dynamic";

export async function POST() {
  return notificationResponse((api) => api.POST("/api/v1/notifications/read-all"));
}
