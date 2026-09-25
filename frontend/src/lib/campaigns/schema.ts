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

/** The browser's datetime-local shape: a Lagos wall-clock time without a zone. */
const DATETIME_LOCAL = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/;

const optionalDatetime = z
  .string()
  .trim()
  .transform((v) => (v === "" ? undefined : v))
  .pipe(
    z
      .string()
      .regex(DATETIME_LOCAL, "Enter a valid date and time")
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
  stored_file_id: z.string().uuid("Upload and clear a creative file before continuing"),
  original_filename: z.string().trim().min(1, "Upload and clear a creative file before continuing"),
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

/** Nigeria observes no daylight saving, so Lagos time is always UTC+01:00. */
const LAGOS_OFFSET_MS = 60 * 60 * 1000;

/**
 * Convert a validated datetime-local value, entered as Lagos wall-clock time, to
 * the instant the API expects. Server actions run in the server's own zone, so the
 * offset is explicit rather than inferred from the runtime.
 */
export function toApiDatetime(value: string | undefined): string | undefined {
  if (!value) return undefined;
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return new Date(`${withSeconds}+01:00`).toISOString();
}

/** Render an API instant as a Lagos datetime-local value for a form default. */
export function toLagosDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const time = Date.parse(iso);
  return Number.isNaN(time) ? "" : new Date(time + LAGOS_OFFSET_MS).toISOString().slice(0, 16);
}
