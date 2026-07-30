import { z } from "zod";

/**
 * Payout-rule form validation, shared by the admin editor's server action.
 * A rule row is valid for exactly one model (backend XOR check, migration
 * 0013): payout_v1 carries the per-km component rates, payout_v2 carries
 * hourly rate + daily payable-hours cap. The backend remains the authority.
 */

export const PAYOUT_MODELS = ["payout_v1", "payout_v2"] as const;
export type PayoutModel = (typeof PAYOUT_MODELS)[number];

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

const hoursCap = z
  .string()
  .trim()
  .transform((v) => (v === "" ? null : v))
  .pipe(
    z
      .string()
      .regex(/^\d+(\.\d{1,2})?$/, "Enter hours like 8 or 7.5")
      .refine((v) => Number(v) > 0 && Number(v) <= 24, "Cap is 0–24 hours")
      .nullable(),
  );

export const V1_FIELDS = [
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

export const V2_FIELDS = ["hourly_rate_naira", "daily_payable_hours_cap"] as const;

export const ruleFormSchema = z
  .object({
    campaign_id: z.string().uuid("Pick a campaign"),
    rule_id: z
      .string()
      .trim()
      .transform((v) => (v === "" ? undefined : v))
      .pipe(z.string().uuid().optional()),
    formula_version: z.enum(PAYOUT_MODELS),
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
    hourly_rate_naira: money,
    daily_payable_hours_cap: hoursCap,
  })
  .superRefine((data, ctx) => {
    if (data.formula_version === "payout_v2") {
      if (data.hourly_rate_naira === null) {
        ctx.addIssue({
          code: "custom",
          path: ["hourly_rate_naira"],
          message: "Hourly rate is required for the hourly model",
        });
      }
      if (data.daily_payable_hours_cap === null) {
        ctx.addIssue({
          code: "custom",
          path: ["daily_payable_hours_cap"],
          message: "Daily payable-hours cap is required (shown in the driver's offer)",
        });
      }
      for (const field of V1_FIELDS) {
        if (data[field] !== null) {
          ctx.addIssue({
            code: "custom",
            path: [field],
            message: "Hourly-model rules cannot set legacy per-km fields",
          });
        }
      }
    } else {
      for (const field of V2_FIELDS) {
        if (data[field] !== null) {
          ctx.addIssue({
            code: "custom",
            path: [field],
            message: "Legacy-model rules cannot set hourly fields",
          });
        }
      }
    }
  });

export type RuleFormValues = z.infer<typeof ruleFormSchema>;
