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

/**
 * Create-revision form (MNY-06A). payout_v2 rule values are immutable — the
 * append-only revision chain is the only value-change path. The backend
 * additionally enforces effective_from strictly after the latest revision
 * and not before the database clock.
 */

const requiredValue = (label: string) =>
  z
    .string()
    .nullable()
    .transform((v, ctx) => {
      if (v === null) {
        ctx.addIssue({ code: "custom", message: `${label} is required` });
        return z.NEVER;
      }
      return v;
    });

export const revisionFormSchema = z.object({
  campaign_id: z.string().uuid("Missing campaign"),
  rule_id: z.string().uuid("Missing rule"),
  hourly_rate_naira: money.pipe(requiredValue("Base hourly rate")),
  premium_hourly_rate_naira: money,
  daily_payable_hours_cap: hoursCap.pipe(requiredValue("Daily payable-hours cap")),
  effective_from: z
    .string()
    .trim()
    .min(1, "Effective-from date and time are required")
    .refine((v) => !Number.isNaN(new Date(v).getTime()), "Enter a valid date and time")
    .refine(
      (v) => new Date(v).getTime() > Date.now(),
      "Effective-from must be in the future — retroactive changes go through a correction order",
    )
    .transform((v) => new Date(v).toISOString()),
  reason: z.string().trim().min(1, "A reason is required — it is recorded in the audit trail"),
});

export type RevisionFormValues = z.infer<typeof revisionFormSchema>;

/**
 * Daily-rate revision form (payout_v4, D39). Every value is entered by
 * Terrax Media staff and none has a default: the client's answers on the
 * shortfall rule, which miles count and the cap are still open. The backend
 * remains the authority (and refuses publication until it is switched on).
 */
const decimalText = (label: string, pattern: RegExp, hint: string) =>
  z.string().trim().min(1, `${label} is required`).regex(pattern, hint);

export const dailyRateFormSchema = z
  .object({
    campaign_id: z.string().uuid("Missing campaign"),
    daily_rate_naira: decimalText(
      "Day rate",
      /^\d+(\.\d{1,2})?$/,
      "Enter the day rate like 10000",
    ).refine((v) => Number(v) > 0, "The day rate must be more than 0"),
    daily_target_miles: decimalText(
      "Daily miles",
      /^\d+(\.\d{1,3})?$/,
      "Enter the daily miles like 70",
    ).refine((v) => Number(v) > 0, "Daily miles must be more than 0"),
    shortfall_strategy: z.enum(["proportional", "per_mile_deduction"], {
      message: "Choose how shorter days are paid",
    }),
    deduction_per_mile_naira: z
      .string()
      .trim()
      .transform((v) => (v === "" ? null : v))
      .pipe(
        z
          .string()
          .regex(/^\d+(\.\d{1,2})?$/, "Enter the deduction like 140")
          .nullable(),
      ),
    minimum_miles: decimalText(
      "Minimum miles",
      /^\d+(\.\d{1,3})?$/,
      "Enter the minimum miles (0 if there is none)",
    ),
    outside_area_weight: decimalText(
      "Miles outside the area",
      /^(0(\.\d{1,4})?|1(\.0{1,4})?)$/,
      "Enter a share from 0 to 1, like 0.5",
    ),
    effective_from: z
      .string()
      .trim()
      .min(1, "Start date and time are required")
      .refine((v) => !Number.isNaN(new Date(v).getTime()), "Enter a valid date and time")
      .refine(
        (v) => new Date(v).getTime() > Date.now(),
        "The start must be in the future — past days change only through a correction",
      )
      .transform((v) => new Date(v).toISOString()),
    reason: z.string().trim().min(1, "A reason is required — it is recorded in the audit trail"),
  })
  .superRefine((data, ctx) => {
    if (data.shortfall_strategy === "per_mile_deduction") {
      if (data.deduction_per_mile_naira === null || Number(data.deduction_per_mile_naira) <= 0) {
        ctx.addIssue({
          code: "custom",
          path: ["deduction_per_mile_naira"],
          message: "Enter the amount taken off for each missing mile",
        });
      }
    } else if (data.deduction_per_mile_naira !== null) {
      ctx.addIssue({
        code: "custom",
        path: ["deduction_per_mile_naira"],
        message: "Leave the per-mile deduction empty when shorter days are paid in proportion",
      });
    }
    if (Number(data.minimum_miles) > Number(data.daily_target_miles)) {
      ctx.addIssue({
        code: "custom",
        path: ["minimum_miles"],
        message: "Minimum miles cannot be more than the daily miles",
      });
    }
  });

export type DailyRateFormValues = z.infer<typeof dailyRateFormSchema>;
