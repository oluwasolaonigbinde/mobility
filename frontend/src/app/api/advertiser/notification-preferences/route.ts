import type { components } from "@/lib/api/schema";
import { notificationResponse } from "../../notifications/_proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return notificationResponse((api) => api.GET("/api/v1/advertiser/notification-preferences"));
}

export async function PATCH(request: Request) {
  const body =
    (await request.json()) as components["schemas"]["AdvertiserNotificationPreferenceUpdate"];
  return notificationResponse((api) =>
    api.PATCH("/api/v1/advertiser/notification-preferences", { body }),
  );
}
