import type { ApiClient } from "./client";
import type { paths } from "./schema";

/** Read failures propagate; callers must show unavailable, never a fabricated zero. */
export const readAdminBadgeSummary = (api: ApiClient) => api.GET("/api/v1/admin/badge-summary");
export const readDriverCurrentJob = (api: ApiClient) => api.GET("/api/v1/driver/current-job");

type OrganizationQuery =
  paths["/api/v1/admin/advertiser-organizations"]["get"]["parameters"]["query"];
type AdminCampaignQuery = paths["/api/v1/admin/campaigns"]["get"]["parameters"]["query"];
type AdvertiserCampaignQuery = paths["/api/v1/advertiser/campaigns"]["get"]["parameters"]["query"];

export const readAdminAdvertiserOrganizations = (api: ApiClient, query?: OrganizationQuery) =>
  api.GET("/api/v1/admin/advertiser-organizations", { params: { query } });
export const readAdminCampaigns = (api: ApiClient, query?: AdminCampaignQuery) =>
  api.GET("/api/v1/admin/campaigns", { params: { query } });
export const readAdvertiserCampaigns = (api: ApiClient, query?: AdvertiserCampaignQuery) =>
  api.GET("/api/v1/advertiser/campaigns", { params: { query } });
export const readAdvertiserRetargetingSources = (api: ApiClient) =>
  api.GET("/api/v1/advertiser/retargeting-sources");
