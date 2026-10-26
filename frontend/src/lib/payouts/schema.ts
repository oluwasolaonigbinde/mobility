import { z } from "zod";

/** Staff enter the day rate, miles, start date and audited reason (D43). */
const decimalText = (label: string, pattern: RegExp, hint: string) =>
  z.string().trim().min(1, `${label} is required`).regex(pattern, hint);

export const dailyRateFormSchema = z.object({
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
});

export type DailyRateFormValues = z.infer<typeof dailyRateFormSchema>;
