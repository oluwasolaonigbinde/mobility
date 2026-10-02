import { cache } from "react";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
export const readDriver = cache(async (id: string) =>
  createApiClient(await getSessionToken()).GET("/api/v1/admin/drivers/{driver_profile_id}", {
    params: { path: { driver_profile_id: id } },
  }),
);
export const readApplication = cache(async (id: string) =>
  createApiClient(await getSessionToken()).GET(
    "/api/v1/admin/driver-applications/{application_id}",
    { params: { path: { application_id: id } } },
  ),
);
export const readCampaign = cache(async (id: string) =>
  createApiClient(await getSessionToken()).GET("/api/v1/admin/campaigns/{campaign_id}", {
    params: { path: { campaign_id: id } },
  }),
);
