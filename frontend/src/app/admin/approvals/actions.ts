"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface CampaignReviewActionState {
  error?: string;
  done?: string;
}

const reviewSchema = z.discriminatedUnion("intent", [
  z.object({ campaign_id: z.string().uuid(), intent: z.literal("approve") }),
  z.object({
    campaign_id: z.string().uuid(),
    intent: z.literal("reject"),
    reason: z.string().trim().min(1, "A rejection reason is required").max(2000),
  }),
]);

export async function reviewCampaignAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = reviewSchema.safeParse({
    campaign_id: String(formData.get("campaign_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid campaign review request." };
  }

  const api = createApiClient(await getSessionToken());
  const path = { params: { path: { campaign_id: parsed.data.campaign_id } } };
  try {
    if (parsed.data.intent === "approve") {
      await api.POST("/api/v1/admin/campaigns/{campaign_id}/approve", path);
    } else {
      await api.POST("/api/v1/admin/campaigns/{campaign_id}/reject", {
        ...path,
        body: { reason: parsed.data.reason },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  revalidatePath("/admin/approvals");
  return { done: parsed.data.intent === "approve" ? "Campaign approved" : "Campaign rejected" };
}

const creativeReviewSchema = z.discriminatedUnion("intent", [
  z.object({ creative_id: z.string().uuid(), intent: z.literal("approve") }),
  z.object({
    creative_id: z.string().uuid(),
    intent: z.literal("reject"),
    reason: z.string().trim().min(1, "A rejection reason is required").max(2000),
  }),
]);

export async function reviewCreativeAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = creativeReviewSchema.safeParse({
    creative_id: String(formData.get("creative_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid creative review request." };
  }

  const api = createApiClient(await getSessionToken());
  const path = { params: { path: { creative_id: parsed.data.creative_id } } };
  try {
    if (parsed.data.intent === "approve") {
      await api.POST("/api/v1/admin/creatives/{creative_id}/approve", path);
    } else {
      await api.POST("/api/v1/admin/creatives/{creative_id}/reject", {
        ...path,
        body: { reason: parsed.data.reason },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  revalidatePath("/admin/approvals");
  return { done: parsed.data.intent === "approve" ? "Creative approved" : "Creative rejected" };
}
