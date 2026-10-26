"use server";

import { z } from "zod";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { askTerraxToCancelCampaign } from "@/lib/api/audit-batch2";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";

export type CancellationRequestState = { error?: string; threadId?: string };
const schema = z.object({
  campaignId: z.uuid(),
  reason: z.string().trim().min(1).max(2000),
  requestId: z.uuid(),
});
export async function requestCampaignCancellation(
  campaignId: string,
  reason: string,
  requestId: string,
): Promise<CancellationRequestState> {
  await requireRole("advertiser");
  const parsed = schema.safeParse({ campaignId, reason, requestId });
  if (!parsed.success) return { error: "Add a short reason, using 2,000 characters or fewer." };
  try {
    const api = createApiClient(await getSessionToken());
    const { data: campaign } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
      params: { path: { campaign_id: campaignId } },
    });
    if (campaign?.id !== campaignId) return { error: "This campaign couldn’t be found." };
    const { data } = await askTerraxToCancelCampaign(
      api,
      campaignId,
      parsed.data.reason,
      requestId,
    );
    if (!data || !z.uuid().safeParse(data.id).success || data.category !== "campaign_cancellation")
      return { error: "We couldn’t confirm your request. Try sending the same request again." };
    revalidatePath("/advertiser/help");
    revalidatePath(`/advertiser/campaigns/${campaignId}`);
    return { threadId: data.id };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && [403, 404].includes(error.status))
      return { error: "This campaign couldn’t be found or isn’t available to your account." };
    if (error instanceof ApiError && error.code === "COMPLAINT_REPLAY_CONFLICT")
      return {
        error: "This request has already been sent with different details. Open Help to check it.",
      };
    return { error: "We couldn’t confirm your request. Try sending the same request again." };
  }
}
