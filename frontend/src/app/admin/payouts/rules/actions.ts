"use server";

import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { ruleFormSchema } from "@/lib/payouts/schema";

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
  revalidatePath("/admin/payouts/rules");
  return { saved: true };
}
