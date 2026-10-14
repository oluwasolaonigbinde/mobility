import { z } from "zod";

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
