"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface RuleActionState {
  error?: string;
  saved?: boolean;
}

const money = z
  .string()
  .trim()
  .transform((v) => (v === "" ? null : v))
  .pipe(
    z
      .string()
      .regex(/^\d+(\.\d{1,4})?$/, "Enter a valid non-negative number")
      .nullable(),
  );

const multiplier = z
  .string()
  .trim()
  .transform((v) => (v === "" ? null : v))
  .pipe(
    z
      .string()
      .regex(/^\d+(\.\d{1,4})?$/, "Enter a multiplier like 0.25")
      .refine((v) => Number(v) <= 1, "Multipliers are 0–1")
      .nullable(),
  );

const ruleSchema = z.object({
  campaign_id: z.string().uuid("Pick a campaign"),
  rule_id: z
    .string()
    .trim()
    .transform((v) => (v === "" ? undefined : v))
    .pipe(z.string().uuid().optional()),
  base_rate_per_km: money,
  base_rate_per_active_hour: money,
  target_zone_bonus_rate_per_km: money,
  bonus_zone_bonus_rate_per_km: money,
  estimated_impression_rate_per_1000: money,
  min_payout_per_trip: money,
  max_payout_per_trip: money,
  low_fraud_multiplier: multiplier,
  medium_fraud_multiplier: multiplier,
  high_fraud_multiplier: multiplier,
});

/** Create a rule, or update the existing one when rule_id is present. */
export async function saveRuleAction(
  _prev: RuleActionState,
  formData: FormData,
): Promise<RuleActionState> {
  const fields = [
    "campaign_id",
    "rule_id",
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
  ] as const;
  const raw = Object.fromEntries(fields.map((f) => [f, String(formData.get(f) ?? "")]));
  const parsed = ruleSchema.safeParse(raw);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };

  const { campaign_id, rule_id, ...body } = parsed.data;
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
        body: { ...body, status: "active" },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/payouts/rules");
  return { saved: true };
}
