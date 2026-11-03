"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { adminStatus } from "@/lib/status/admin";
import { formatMoney } from "@/lib/format";

export interface ProcessTripState {
  error?: string;
  /** Human summary of what each completed step produced. */
  steps?: string[];
}

const tripIdSchema = z.string().uuid("Enter a valid trip ID");

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
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Enter a valid trip ID" };
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
        ? `Trip recalculated: ${(Number(analytics.distance_m ?? 0) / 1609.344).toFixed(1)} miles`
        : "Trip recalculated",
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
        ? `Estimated views: ${Math.round(Number(estimate.estimated_impressions ?? 0)).toLocaleString()}`
        : "Views estimated",
    );

    const { data: payout } = await api.POST("/api/v1/admin/trips/{trip_id}/calculate-payout", {
      params: { path: { trip_id: tripId } },
      body: {},
    });
    steps.push(
      payout
        ? `Trip pay: ${formatMoney(payout.final_payout, payout.currency)} · Status: ${adminStatus(payout.ledger_entry?.status)}`
        : "Trip pay calculated",
    );
  } catch (error) {
    unstable_rethrow(error);
    const reason =
      error instanceof ApiError
        ? publicActionError(error)
        : "Could not reach the server. Try again.";
    return { error: `${reason}${steps.length ? ` (completed: ${steps.join(" · ")})` : ""}`, steps };
  }

  revalidatePath("/admin/money");
  revalidatePath("/admin/drivers/[driverId]", "page");
  return { steps };
}
