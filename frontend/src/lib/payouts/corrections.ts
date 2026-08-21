import { z } from "zod";

/**
 * Correction-order forms (MNY-06C). Direct day recompute is retired — every
 * retroactive recompute is projected into a maker-checker correction order
 * (creator submits, a different admin approves, any admin executes). The
 * backend is the authority on every transition; this module only validates
 * form input and renders the stored projection defensively.
 */

export const correctionOrderFormSchema = z.object({
  campaign_id: z.string().uuid("Pick a campaign"),
  lagos_day: z
    .string()
    .trim()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Pick the Lagos day to correct"),
  reason: z.string().trim(),
});

export type CorrectionOrderFormValues = z.infer<typeof correctionOrderFormSchema>;

export interface ProjectedDeltaSummary {
  previousTotal: string;
  targetTotal: string;
  deltaTotal: string;
  adjustmentCount: number;
  reversalCount: number;
  tripCount: number;
  currency: string;
}

/**
 * The API types projected_delta as an opaque JSON object; the backend writes
 * {currencies, trips[], day_totals}. Parse defensively — a missing or
 * malformed payload renders as "no projection" instead of crashing.
 */
export function summarizeProjectedDelta(delta: unknown): ProjectedDeltaSummary | null {
  if (typeof delta !== "object" || delta === null) return null;
  const totals = (delta as { day_totals?: unknown }).day_totals;
  if (typeof totals !== "object" || totals === null) return null;
  const t = totals as Record<string, unknown>;
  const money = (v: unknown) => (typeof v === "string" ? v : null);
  const count = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const previousTotal = money(t.previous_posted_amount);
  const targetTotal = money(t.target_amount);
  const deltaTotal = money(t.delta_amount);
  if (previousTotal === null || targetTotal === null || deltaTotal === null) return null;
  const currencies = (delta as { currencies?: unknown }).currencies;
  const currency =
    Array.isArray(currencies) && typeof currencies[0] === "string" ? currencies[0] : "NGN";
  return {
    previousTotal,
    targetTotal,
    deltaTotal,
    adjustmentCount: count(t.projected_adjustment_count) ?? 0,
    reversalCount: count(t.projected_reversal_count) ?? 0,
    tripCount: count(t.trip_count) ?? 0,
    currency,
  };
}
