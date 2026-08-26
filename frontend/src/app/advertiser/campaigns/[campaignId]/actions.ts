"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

const submitSchema = z.object({
  campaignId: z.string().uuid(),
});

const creativeSubmitSchema = submitSchema.extend({
  creativeId: z.string().uuid(),
});

export interface CampaignReviewActionState {
  error?: string;
  done?: string;
}

export async function submitCampaignForReviewAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = submitSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
  });
  if (!parsed.success) {
    return { error: "Invalid campaign review request." };
  }

  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/submit", {
      params: { path: { campaign_id: parsed.data.campaignId } },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    return { error: "Could not reach the server. Please try again." };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/advertiser/campaigns");
  return { done: "Campaign submitted for admin review." };
}

export async function submitCreativeForReviewAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = creativeSubmitSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
    creativeId: String(formData.get("creative_id") ?? ""),
  });
  if (!parsed.success) {
    return { error: "Invalid creative review request." };
  }

  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/submit", {
      params: {
        path: {
          campaign_id: parsed.data.campaignId,
          creative_id: parsed.data.creativeId,
        },
      },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    return { error: "Could not reach the server. Please try again." };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/admin/approvals");
  return { done: "Creative submitted for admin review." };
}
