import { z } from "zod";

/**
 * Campaign form validation — shared by the client wizard (instant feedback)
 * and the server action (authoritative re-validation). Mirrors backend
 * rules: name required, start < end, non-negative money.
 */

const moneyString = z
  .string()
  .trim()
  .regex(/^\d+(\.\d{1,2})?$/, "Enter a valid amount (e.g. 250000 or 250000.50)")
  .refine((v) => Number(v) >= 0, "Amount cannot be negative");

/** Optional money input: empty string means "not set". */
const optionalMoney = z
  .string()
  .trim()
  .transform((v) => (v === "" ? undefined : v))
  .pipe(moneyString.optional());

const optionalDatetime = z
  .string()
  .trim()
  .transform((v) => (v === "" ? undefined : v))
  .pipe(
    z
      .string()
      .refine((v) => !Number.isNaN(Date.parse(v)), "Enter a valid date and time")
      .optional(),
  );

export const campaignBasicsSchema = z
  .object({
    name: z.string().trim().min(1, "Campaign name is required").max(255, "Name is too long"),
    description: z
      .string()
      .trim()
      .max(2000, "Description is too long")
      .transform((v) => (v === "" ? undefined : v))
      .optional(),
    start_at: optionalDatetime,
    end_at: optionalDatetime,
    budget_amount: optionalMoney,
    daily_budget_amount: optionalMoney,
  })
  .superRefine((data, ctx) => {
    if (data.start_at && data.end_at && Date.parse(data.start_at) >= Date.parse(data.end_at)) {
      ctx.addIssue({
        code: "custom",
        path: ["end_at"],
        message: "End must be after start",
      });
    }
  });

export const creativeSchema = z.object({
  name: z.string().trim().min(1, "Creative name is required").max(255),
  creative_type: z.enum(["image", "video", "html", "text", "other"]),
  placement: z.enum(["vehicle_exterior", "vehicle_interior", "digital_screen", "print", "other"]),
  asset_url: z
    .string()
    .trim()
    .transform((v) => (v === "" ? undefined : v))
    .pipe(z.string().url("Enter a valid URL (https://…)").optional()),
});

export const campaignWizardSchema = z.object({
  basics: campaignBasicsSchema,
  creatives: z.array(creativeSchema).max(10, "At most 10 creatives at creation"),
});

export type CampaignBasicsInput = z.input<typeof campaignBasicsSchema>;
export type CampaignBasics = z.output<typeof campaignBasicsSchema>;
export type CreativeInput = z.input<typeof creativeSchema>;
export type CampaignWizardInput = z.input<typeof campaignWizardSchema>;
export type CampaignWizard = z.output<typeof campaignWizardSchema>;

/** Convert a validated datetime-local string to the ISO-8601 the API expects. */
export function toApiDatetime(value: string | undefined): string | undefined {
  return value ? new Date(value).toISOString() : undefined;
}
