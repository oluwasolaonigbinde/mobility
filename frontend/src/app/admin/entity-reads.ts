import { cache } from "react";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
export const readAdvertiserCompany = cache(async (id: string) =>
  createApiClient(await getSessionToken()).GET(
    "/api/v1/admin/advertiser-organizations/{organization_id}/company",
    { params: { path: { organization_id: id } } },
  ),
);
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
// One commercial read per request, shared by the campaign hub and its Money and invoice sections.
export const readCampaignCommercial = cache(async (id: string) =>
  createApiClient(await getSessionToken()).GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
    params: { path: { campaign_id: id } },
  }),
);
