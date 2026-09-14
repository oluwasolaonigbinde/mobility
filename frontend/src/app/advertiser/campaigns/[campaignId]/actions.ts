"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { publicActionError } from "@/lib/api/public-action-error";
import { getSessionToken } from "@/lib/auth/session";

const submitSchema = z.object({
  campaignId: z.string().uuid(),
});

const creativeSubmitSchema = submitSchema.extend({
  creativeId: z.string().uuid(),
});

const creativeReplaceSchema = creativeSubmitSchema.extend({
  storedFileId: z.string().uuid(),
  creativeType: z.enum(["image", "video", "other"]),
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
  commandId?: string;
  error?: string;
  done?: string;
  confirmedRequest?: components["schemas"]["CampaignChangeRead"];
  preview?: components["schemas"]["CampaignChangePreviewRead"];
  proposal?: {
    budgetAmount?: string;
    dailyBudgetAmount?: string;
    startAt?: string;
    endAt?: string;
    reason: string;
  };
}

const campaignActionErrors = {
  CAMPAIGN_CHANGE_NOOP: "Enter a change that differs from the current campaign.",
  CAMPAIGN_CHANGE_RETROACTIVE_DATE: "Choose a future campaign date.",
  INVALID_CAMPAIGN_WINDOW: "The campaign start must remain before its end.",
  INVALID_CAMPAIGN_BUDGET: "The daily budget cannot exceed the total budget.",
  CAMPAIGN_CHANGE_STALE: "Campaign details changed. Preview the change again.",
  CAMPAIGN_CHANGE_PREVIEW_STALE: "Funding or review facts changed. Preview the change again.",
  CAMPAIGN_CHANGE_RETRY_CONFLICT: "This confirmation no longer matches the preview. Preview again.",
  CAMPAIGN_REVIEW_STATE_CONFLICT: "The campaign state changed. Refresh and try again.",
  CREATIVE_REVIEW_STATE_CONFLICT: "The creative state changed. Refresh and try again.",
  CREATIVE_FILE_NOT_CLEARED: "The creative file is not ready for review.",
} as const;

function safeCampaignError(error: unknown, fallback: string) {
  return publicActionError(error, campaignActionErrors, fallback);
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
    return { error: safeCampaignError(error, "Could not cancel the campaign. Try again.") };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/advertiser/campaigns");
  return { done: "Campaign cancelled at the recorded financial cutoff." };
}

export async function previewCampaignChangeAction(
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
    const { data } = await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/change-preview", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body,
    });
    if (!data) return { error: "The preview is unavailable. Try again." };
    return {
      commandId: parsed.data.clientRequestId,
      preview: data,
      proposal: {
        budgetAmount: parsed.data.budgetAmount || undefined,
        dailyBudgetAmount: parsed.data.dailyBudgetAmount || undefined,
        startAt: parsed.data.startAt || undefined,
        endAt: parsed.data.endAt || undefined,
        reason: parsed.data.reason,
      },
    };
  } catch (error) {
    return { error: safeCampaignError(error, "Could not preview the change. Try again.") };
  }
}

export async function confirmCampaignChangeAction(
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
  const sourceSha256 = String(formData.get("source_sha256") ?? "");
  const previewSha256 = String(formData.get("preview_sha256") ?? "");
  if (
    !parsed.success ||
    !/^[0-9a-f]{64}$/.test(sourceSha256) ||
    !/^[0-9a-f]{64}$/.test(previewSha256)
  ) {
    return { error: "This preview is invalid. Preview the change again." };
  }
  const body = {
    client_request_id: parsed.data.clientRequestId,
    source_sha256: sourceSha256,
    preview_sha256: previewSha256,
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
    const { data } = await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/change-requests", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body,
    });
    if (!data) return { error: "The confirmation result is unavailable. Preview again." };
    revalidatePath("/admin/approvals");
    return {
      commandId: parsed.data.clientRequestId,
      done: "Campaign change confirmed.",
      confirmedRequest: data,
    };
  } catch (error) {
    return { error: safeCampaignError(error, "Could not confirm the change. Try again.") };
  }
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
    return { error: safeCampaignError(error, "Could not submit the campaign. Try again.") };
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
    return { error: safeCampaignError(error, "Could not submit the creative. Try again.") };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/admin/approvals");
  return { done: "Creative submitted for admin review." };
}

export async function replaceCreativeAndSubmitAction(
  _previous: CampaignReviewActionState,
  formData: FormData,
): Promise<CampaignReviewActionState> {
  const parsed = creativeReplaceSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
    creativeId: String(formData.get("creative_id") ?? ""),
    storedFileId: String(formData.get("stored_file_id") ?? ""),
    creativeType: String(formData.get("creative_type") ?? ""),
  });
  if (!parsed.success) {
    return { error: "Upload and clear replacement artwork before submitting." };
  }

  const api = createApiClient(await getSessionToken());
  const path = {
    campaign_id: parsed.data.campaignId,
    creative_id: parsed.data.creativeId,
  };
  try {
    await api.PATCH("/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}", {
      params: { path },
      body: {
        stored_file_id: parsed.data.storedFileId,
        creative_type: parsed.data.creativeType,
      },
    });
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/submit", {
      params: { path },
    });
  } catch (error) {
    return {
      error: safeCampaignError(
        error,
        "The artwork result is not yet confirmed. Retry to safely continue the same replacement.",
      ),
    };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/admin/approvals");
  return { done: "Replacement artwork submitted for admin review." };
}
