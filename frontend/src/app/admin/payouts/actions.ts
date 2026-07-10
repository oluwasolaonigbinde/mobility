"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoney } from "@/lib/format";

export interface ProcessTripState {
  error?: string;
  /** Human summary of what each completed step produced. */
  steps?: string[];
}

const tripIdSchema = z.string().uuid("Enter a valid trip ID (UUID)");

/**
 * The full trip → money pipeline, in order:
 *   1. recompute route analytics (distance, zones, quality, fraud checks)
 *   2. estimate impressions from the analyzed route
 *   3. calculate the payout and write the ledger entry
 * Each step is idempotent on the backend; running it again refreshes the
 * downstream artifacts.
 */
export async function processTripAction(
  _prev: ProcessTripState,
  formData: FormData,
): Promise<ProcessTripState> {
  const parsed = tripIdSchema.safeParse(String(formData.get("trip_id") ?? "").trim());
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid trip ID" };
  const tripId = parsed.data;

  const api = createApiClient(await getSessionToken());
  const steps: string[] = [];

  try {
    const { data: analytics } = await api.POST(
      "/api/v1/admin/trips/{trip_id}/recompute-analytics",
      {
        params: { path: { trip_id: tripId } },
        body: {},
      },
    );
    steps.push(
      analytics
        ? `Analytics: ${analytics.valid_ping_count}/${analytics.ping_count} valid pings, ${(Number(analytics.distance_m ?? 0) / 1000).toFixed(1)} km, quality ${analytics.quality_score ?? "—"}${(analytics.fraud_flags ?? []).length ? `, ${(analytics.fraud_flags ?? []).length} fraud flag(s)` : ""}`
        : "Analytics recomputed",
    );

    const { data: estimate } = await api.POST(
      "/api/v1/admin/trips/{trip_id}/estimate-impressions",
      {
        params: { path: { trip_id: tripId } },
        body: {},
      },
    );
    steps.push(
      estimate
        ? `Impressions: ${Math.round(Number(estimate.estimated_impressions ?? 0)).toLocaleString()} estimated (confidence ${estimate.confidence_score ?? "—"})`
        : "Impressions estimated",
    );

    const { data: payout } = await api.POST("/api/v1/admin/trips/{trip_id}/calculate-payout", {
      params: { path: { trip_id: tripId } },
      body: {},
    });
    steps.push(
      payout
        ? `Payout: ${formatMoney(payout.final_payout, payout.currency)} → ledger (${payout.ledger_entry?.status ?? "created"})`
        : "Payout calculated",
    );
  } catch (error) {
    const reason = error instanceof ApiError ? error.message : "server unreachable";
    return { error: `${reason}${steps.length ? ` (completed: ${steps.join(" · ")})` : ""}`, steps };
  }

  revalidatePath("/admin/payouts");
  return { steps };
}
