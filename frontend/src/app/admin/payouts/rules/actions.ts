"use server";

import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { dailyRateFormSchema, revisionFormSchema, ruleFormSchema } from "@/lib/payouts/schema";

export interface RuleActionState {
  error?: string;
  saved?: boolean;
}

/**
 * Create a rule, or update the existing one when rule_id is present.
 * A rule row's model is immutable (backend rejects cross-model fields), so
 * the form clears rule_id when the admin switches model — saving then creates
 * a new active rule that replaces (deactivates) the current one.
 */
export async function saveRuleAction(
  _prev: RuleActionState,
  formData: FormData,
): Promise<RuleActionState> {
  const fields = [
    "campaign_id",
    "rule_id",
    "formula_version",
    "base_rate_per_km",
    "base_rate_per_active_hour",
    "target_zone_bonus_rate_per_km",
    "bonus_zone_bonus_rate_per_km",
    "estimated_impression_rate_per_1000",
    "min_payout_per_trip",
    "max_payout_per_trip",
    "low_fraud_multiplier",
    "medium_fraud_multiplier",
    "high_fraud_multiplier",
    "hourly_rate_naira",
    "daily_payable_hours_cap",
  ] as const;
  const raw = Object.fromEntries(fields.map((f) => [f, String(formData.get(f) ?? "")]));
  const parsed = ruleFormSchema.safeParse(raw);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };

  const { campaign_id, rule_id, formula_version, ...values } = parsed.data;
  const body =
    formula_version === "payout_v2"
      ? {
          hourly_rate_naira: values.hourly_rate_naira,
          daily_payable_hours_cap: values.daily_payable_hours_cap,
        }
      : {
          base_rate_per_km: values.base_rate_per_km,
          base_rate_per_active_hour: values.base_rate_per_active_hour,
          target_zone_bonus_rate_per_km: values.target_zone_bonus_rate_per_km,
          bonus_zone_bonus_rate_per_km: values.bonus_zone_bonus_rate_per_km,
          estimated_impression_rate_per_1000: values.estimated_impression_rate_per_1000,
          min_payout_per_trip: values.min_payout_per_trip,
          max_payout_per_trip: values.max_payout_per_trip,
          low_fraud_multiplier: values.low_fraud_multiplier,
          medium_fraud_multiplier: values.medium_fraud_multiplier,
          high_fraud_multiplier: values.high_fraud_multiplier,
        };
  try {
    const api = createApiClient(await getSessionToken());
    if (rule_id) {
      await api.PATCH("/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}", {
        params: { path: { campaign_id, rule_id } },
        body,
      });
    } else {
      await api.POST("/api/v1/admin/campaigns/{campaign_id}/payout-rules", {
        params: { path: { campaign_id } },
        body: { ...body, formula_version, status: "active" },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  return { saved: true };
}

export interface RevisionActionState {
  error?: string;
  created?: boolean;
}

/**
 * Append an effective-dated revision to a campaign's hourly value chain
 * (MNY-06A). Rule values themselves are immutable — the backend 409s any
 * edit-in-place — so this is the only value-change path. Envelope errors
 * (retro-insertion, concurrent supersede) are surfaced verbatim.
 */
export async function createRevisionAction(
  _prev: RevisionActionState,
  formData: FormData,
): Promise<RevisionActionState> {
  const fields = [
    "campaign_id",
    "rule_id",
    "hourly_rate_naira",
    "premium_hourly_rate_naira",
    "daily_payable_hours_cap",
    "effective_from",
    "reason",
  ] as const;
  const raw = Object.fromEntries(fields.map((f) => [f, String(formData.get(f) ?? "")]));
  const parsed = revisionFormSchema.safeParse(raw);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };

  const { campaign_id, rule_id, ...values } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}/revisions", {
      params: { path: { campaign_id, rule_id } },
      body: {
        hourly_rate_naira: values.hourly_rate_naira,
        premium_hourly_rate_naira: values.premium_hourly_rate_naira,
        daily_payable_hours_cap: values.daily_payable_hours_cap,
        effective_from: values.effective_from,
        reason: values.reason,
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  return { created: true };
}

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
