"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import {
  correctionOrderFormSchema,
  summarizeProjectedDelta,
  type ProjectedDeltaSummary,
} from "@/lib/payouts/corrections";

export interface NewOrderState {
  error?: string;
  /** Read-only day projection preview (GET day-projection). */
  projection?: ProjectedDeltaSummary & {
    campaignId: string;
    lagosDay: string;
    fingerprint: string;
  };
  created?: boolean;
}

/**
 * Two-intent form: "project" previews the day's delta read-only; "create"
 * turns campaign + Lagos day + reason into a draft correction order (the
 * backend stores its own authoritative projection at that moment).
 */
export async function newOrderAction(
  _prev: NewOrderState,
  formData: FormData,
): Promise<NewOrderState> {
  const parsed = correctionOrderFormSchema.safeParse({
    campaign_id: String(formData.get("campaign_id") ?? ""),
    lagos_day: String(formData.get("lagos_day") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  const { campaign_id, lagos_day, reason } = parsed.data;
  const intent = String(formData.get("intent") ?? "project");

  const api = createApiClient(await getSessionToken());
  try {
    if (intent === "create") {
      if (!reason) return { error: "A reason is required — it is recorded in the audit trail" };
      await api.POST("/api/v1/admin/payouts/correction-orders", {
        body: { campaign_id, lagos_day, reason },
      });
      revalidatePath("/admin/payouts/corrections");
      return { created: true };
    }
    const { data } = await api.GET("/api/v1/admin/payouts/day-projection", {
      params: { query: { campaign_id, lagos_day } },
    });
    const summary = data ? summarizeProjectedDelta(data.projected_delta) : null;
    if (!data || !summary) return { error: "The projection came back in an unexpected shape." };
    return {
      projection: {
        ...summary,
        campaignId: campaign_id,
        lagosDay: lagos_day,
        fingerprint: data.projection_fingerprint,
      },
    };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
}

export interface OrderActionState {
  error?: string;
  done?: string;
}

const transitionSchema = z.object({
  order_id: z.string().uuid(),
  intent: z.enum(["submit", "approve", "reject", "execute"]),
});

/**
 * Maker-checker transitions (Q22): only the creator submits, a different
 * admin approves, any admin rejects or executes. The backend enforces every
 * rule (403/409); its envelope messages are surfaced verbatim as the truth.
 */
export async function orderTransitionAction(
  _prev: OrderActionState,
  formData: FormData,
): Promise<OrderActionState> {
  const parsed = transitionSchema.safeParse({
    order_id: String(formData.get("order_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
  });
  if (!parsed.success) return { error: "Invalid request" };
  const { order_id, intent } = parsed.data;

  const api = createApiClient(await getSessionToken());
  const path = { params: { path: { order_id } } };
  try {
    if (intent === "submit") {
      await api.POST("/api/v1/admin/payouts/correction-orders/{order_id}/submit", path);
    } else if (intent === "approve") {
      await api.POST("/api/v1/admin/payouts/correction-orders/{order_id}/approve", path);
    } else if (intent === "reject") {
      await api.POST("/api/v1/admin/payouts/correction-orders/{order_id}/reject", path);
    } else {
      const rawReleaseAt = String(formData.get("release_at") ?? "").trim();
      let release_at: string | null = null;
      if (rawReleaseAt) {
        const releaseDate = new Date(rawReleaseAt);
        if (Number.isNaN(releaseDate.getTime())) {
          return { error: "Enter a valid release date and time" };
        }
        release_at = releaseDate.toISOString();
      }
      await api.POST("/api/v1/admin/payouts/correction-orders/{order_id}/execute", {
        ...path,
        body: { release_at },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/payouts/corrections");
  const done: Record<typeof intent, string> = {
    submit: "Submitted for approval",
    approve: "Approved — any admin can now execute",
    reject: "Rejected",
    execute: "Executed — ledger differentials written",
  };
  return { done: done[intent] };
}
