"use server";

import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { dailyRateFormSchema } from "@/lib/payouts/schema";

export interface DailyRateActionState {
  error?: string;
  field?: string;
  notSwitchedOn?: boolean;
  created?: boolean;
  // Echoed back so a refused form keeps what the admin typed.
  values?: Record<string, string>;
}

/**
 * Publish a daily-rate (payout_v4) revision. The server creates the campaign's
 * daily-rate rule on first use, fixes the 5-minute stop rule, and refuses
 * everything (503) until publishing is switched on.
 */
export async function publishDailyRateAction(
  _prev: DailyRateActionState,
  formData: FormData,
): Promise<DailyRateActionState> {
  const fields = [
    "campaign_id",
    "daily_rate_naira",
    "daily_target_miles",
    "shortfall_strategy",
    "deduction_per_mile_naira",
    "minimum_miles",
    "outside_area_weight",
    "effective_from",
    "reason",
  ] as const;
  const raw = Object.fromEntries(fields.map((f) => [f, String(formData.get(f) ?? "")]));
  const parsed = dailyRateFormSchema.safeParse(raw);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    return { error: issue?.message ?? "Invalid input", field: issue?.path.join("."), values: raw };
  }
  const { campaign_id, ...body } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaigns/{campaign_id}/payout-v4-revisions", {
      params: { path: { campaign_id } },
      body,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 503) return { notSwitchedOn: true, values: raw };
      return { error: error.message, values: raw };
    }
    return { error: "Could not reach the server. Try again.", values: raw };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  return { created: true };
}
