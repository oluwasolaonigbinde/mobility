import { notificationResponse } from "../../_proxy";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  context: { params: Promise<{ notificationId: string }> },
) {
  const { notificationId } = await context.params;
  return notificationResponse((api) =>
    api.POST("/api/v1/notifications/{notification_id}/read", {
      params: { path: { notification_id: notificationId } },
    }),
  );
}
