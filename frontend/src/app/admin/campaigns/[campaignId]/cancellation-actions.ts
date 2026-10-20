"use server";
import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { createApiClient } from "@/lib/api/client";
import { cancelCampaignAsStaff } from "@/lib/api/audit-batch2";
import { ApiError } from "@/lib/api/errors";

const schema = z.object({
  campaignId: z.uuid(),
  reason: z.string().trim().min(1).max(1000),
  requestId: z.uuid(),
  complaintId: z.uuid().optional(),
});
export type StaffCancellationState = { error?: string; done?: string };
export async function cancelWholeCampaign(
  input: z.input<typeof schema>,
): Promise<StaffCancellationState> {
  await requireRole("admin");
  const parsed = schema.safeParse(input);
  if (!parsed.success) return { error: "Add a reason using 1–1,000 characters." };
  const { campaignId, reason, requestId, complaintId } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    const { data: campaign } = await api.GET("/api/v1/admin/campaigns/{campaign_id}", {
      params: { path: { campaign_id: campaignId } },
    });
    if (campaign?.id !== campaignId) return { error: "This campaign couldn’t be found." };
    if (complaintId) {
      const { data: request } = await api.GET("/api/v1/admin/complaints/{complaint_id}", {
        params: { path: { complaint_id: complaintId } },
      });
      if (
        !request ||
        request.id !== complaintId ||
        request.category !== "campaign_cancellation" ||
        request.reference_type !== "campaign" ||
        request.reference_id !== campaignId ||
        request.advertiser_organization_id !== campaign.organization_id
      )
        return { error: "This cancellation request doesn’t belong to this campaign." };
    }
    if (campaign.status === "cancelled")
      return {
        done: "This campaign has already been cancelled. Review billing for any settlement.",
      };
    const { data } = await cancelCampaignAsStaff(api, campaignId, {
      reason,
      clientRequestId: requestId,
      complaintId,
    });
    if (!data || data.campaign_id !== campaignId || !Number.isFinite(Date.parse(data.cutoff_at)))
      return {
        error:
          "Cancellation couldn’t be confirmed. Retry with the same reason to check this request.",
      };
    for (const path of [
      `/admin/campaigns/${campaignId}`,
      "/admin/campaigns",
      "/admin/support",
      `/admin/billing/${campaignId}`,
      `/advertiser/campaigns/${campaignId}`,
    ])
      revalidatePath(path);
    return { done: "Campaign cancelled. Review billing for any settlement." };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && [403, 404].includes(error.status))
      return { error: "This campaign or cancellation request isn’t available." };
    return {
      error:
        "Cancellation couldn’t be confirmed. Retry with the same reason to check this request.",
    };
  }
}
