import type { ApiClient } from "@/lib/api/client";
export async function readTripContext(
  api: ApiClient,
  tripId: string,
  scope: { driver_profile_id?: string; campaign_id?: string; assignment_id?: string } = {},
) {
  const { data: analytics } = await api.GET("/api/v1/admin/trips/{trip_id}/analytics", {
    params: { path: { trip_id: tripId } },
  });
  if (
    !analytics ||
    analytics.trip_session_id !== tripId ||
    !analytics.started_at ||
    (scope.driver_profile_id && analytics.driver_profile_id !== scope.driver_profile_id) ||
    (scope.campaign_id && analytics.campaign_id !== scope.campaign_id) ||
    (scope.assignment_id && analytics.assignment_id !== scope.assignment_id)
  )
    throw new Error("Invalid trip context");
  const { data: job } = await api.GET("/api/v1/admin/campaign-assignments/{assignment_id}", {
    params: { path: { assignment_id: analytics.assignment_id } },
  });
  if (
    !job ||
    job.id !== analytics.assignment_id ||
    job.driver_profile_id !== analytics.driver_profile_id ||
    job.campaign_id !== analytics.campaign_id ||
    !job.driver_profile?.full_name ||
    !job.campaign?.name ||
    !job.vehicle?.plate_number
  )
    throw new Error("Incomplete trip context");
  return {
    analytics,
    job,
    name: job.driver_profile.full_name,
    campaign: job.campaign.name,
    plate: job.vehicle.plate_number,
    date: analytics.started_at,
  };
}
