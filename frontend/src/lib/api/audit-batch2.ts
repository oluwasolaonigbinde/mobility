import type { ApiClient } from "./client";
import type { components, paths } from "./schema";

type EnquiryQuery = paths["/api/v1/admin/campaign-enquiries"]["get"]["parameters"]["query"];
type ReportQuery =
  paths["/api/v1/advertiser/campaigns/{campaign_id}/report"]["get"]["parameters"]["query"];

/** D103: the booked total behind the budget alerts, on every advertiser campaign read. */
export type BudgetUsed = components["schemas"]["BudgetUsedRead"];
export type ApplicationContinuation = components["schemas"]["ApplicationContinuationRead"];

export const readCampaignPerformance = (api: ApiClient, campaignId: string, query?: ReportQuery) =>
  api.GET("/api/v1/advertiser/campaigns/{campaign_id}/report", {
    params: { path: { campaign_id: campaignId }, query },
  });
export const rerunCampaignReport = (api: ApiClient, campaignId: string) =>
  api.POST("/api/v1/admin/campaigns/{campaign_id}/reports/re-run", {
    params: { path: { campaign_id: campaignId } },
  });
export const readStaffEnquiries = (api: ApiClient, query?: EnquiryQuery) =>
  api.GET("/api/v1/admin/campaign-enquiries", { params: { query } });
export const readStaffEnquiry = (api: ApiClient, enquiryId: string) =>
  api.GET("/api/v1/admin/campaign-enquiries/{enquiry_id}", {
    params: { path: { enquiry_id: enquiryId } },
  });
export const createAdvertiserFromEnquiry = (
  api: ApiClient,
  enquiryId: string,
  ownerUserId?: string | null,
) =>
  api.POST("/api/v1/admin/campaign-enquiries/{enquiry_id}/create-advertiser", {
    params: { path: { enquiry_id: enquiryId } },
    body: { owner_user_id: ownerUserId },
  });
export const continueDriverApplication = (api: ApiClient, applicationAccessToken: string) =>
  api.POST("/api/v1/auth/driver-onboarding/continue", {
    body: { application_access_token: applicationAccessToken },
  });

export const readDriverJobArtwork = (api: ApiClient, assignmentId: string) =>
  api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/artwork/download", {
    params: { path: { assignment_id: assignmentId } },
  });

export const askTerraxToCancelCampaign = (
  api: ApiClient,
  campaignId: string,
  reason: string,
  clientRequestId: string,
) =>
  api.POST("/api/v1/advertiser/complaints", {
    body: {
      category: "campaign_cancellation",
      message: reason,
      reference_type: "campaign",
      reference_id: campaignId,
      client_request_id: clientRequestId,
    },
  });

/**
 * REQ-194: this campaign's support threads. A request is pending while it is a
 * campaign_cancellation, not resolved, and the campaign is neither cancelled nor completed.
 */
export const readCampaignCancellationRequests = (api: ApiClient, campaignId: string) =>
  api.GET("/api/v1/advertiser/complaints", { params: { query: { campaign_id: campaignId } } });

export const cancelCampaignAsStaff = (
  api: ApiClient,
  campaignId: string,
  input: { reason: string; clientRequestId: string; complaintId?: string | null },
) =>
  api.POST("/api/v1/admin/campaigns/{campaign_id}/cancel", {
    params: { path: { campaign_id: campaignId } },
    body: {
      reason: input.reason,
      client_request_id: input.clientRequestId,
      complaint_id: input.complaintId,
    },
  });
