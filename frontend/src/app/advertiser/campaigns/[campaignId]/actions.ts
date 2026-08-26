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

const cancellationSchema = z.object({
  campaignId: z.string().uuid(),
  clientRequestId: z.string().uuid(),
  reason: z.string().trim().min(1, "A cancellation reason is required").max(1000),
  confirmed: z.literal("on", "Confirm that you understand cancellation is permanent"),
});

const optionalLagosDateTime = z
  .string()
  .trim()
  .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
  .optional()
  .or(z.literal(""));

const changeSchema = z
  .object({
    campaignId: z.string().uuid(),
    clientRequestId: z.string().uuid(),
    budgetAmount: z
      .string()
      .trim()
      .regex(/^\d+(\.\d{1,2})?$/)
      .optional()
      .or(z.literal("")),
    dailyBudgetAmount: z
      .string()
      .trim()
      .regex(/^\d+(\.\d{1,2})?$/)
      .optional()
      .or(z.literal("")),
    startAt: optionalLagosDateTime,
    endAt: optionalLagosDateTime,
    reason: z.string().trim().min(1, "A reason is required").max(1000),
  })
  .refine(
    ({ budgetAmount, dailyBudgetAmount, startAt, endAt }) =>
      Boolean(budgetAmount || dailyBudgetAmount || startAt || endAt),
    "Enter at least one change.",
  );

export interface CampaignReviewActionState {
  error?: string;
  done?: string;
}

function lagosDateTime(value: string | undefined): string | undefined {
  if (!value) return undefined;
  return new Date(`${value}:00+01:00`).toISOString();
}

export async function requestCampaignCancellationAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = cancellationSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
    clientRequestId: String(formData.get("client_request_id") ?? ""),
    reason: String(formData.get("reason") ?? ""),
    confirmed: String(formData.get("confirmed") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid campaign cancellation request." };
  }

  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/cancel", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body: {
        client_request_id: parsed.data.clientRequestId,
        reason: parsed.data.reason,
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server. Please try again." };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/advertiser/campaigns");
  return { done: "Campaign cancelled at the recorded financial cutoff." };
}

export async function requestCampaignChangeAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = changeSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
    clientRequestId: String(formData.get("client_request_id") ?? ""),
    budgetAmount: String(formData.get("budget_amount") ?? ""),
    dailyBudgetAmount: String(formData.get("daily_budget_amount") ?? ""),
    startAt: String(formData.get("start_at") ?? ""),
    endAt: String(formData.get("end_at") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid campaign change request." };
  }
  const body = {
    client_request_id: parsed.data.clientRequestId,
    reason: parsed.data.reason,
    ...(parsed.data.budgetAmount ? { budget_amount: parsed.data.budgetAmount } : {}),
    ...(parsed.data.dailyBudgetAmount
      ? { daily_budget_amount: parsed.data.dailyBudgetAmount }
      : {}),
    ...(parsed.data.startAt ? { start_at: lagosDateTime(parsed.data.startAt) } : {}),
    ...(parsed.data.endAt ? { end_at: lagosDateTime(parsed.data.endAt) } : {}),
  };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/change-requests", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body,
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server. Please try again." };
  }
  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/admin/approvals");
  return { done: "Campaign change recorded." };
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
