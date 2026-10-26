"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
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
      revalidatePath("/admin/money");
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
    unstable_rethrow(error);
    if (error instanceof ApiError) return { error: publicActionError(error) };
    return { error: "Could not reach the server." };
  }
}

export interface OrderActionState {
  error?: string;
  done?: string;
}

const transitionSchema = z.object({
  order_id: z.string().uuid(),
  reason: z.string().trim().min(3).max(500),
});

export async function orderTransitionAction(
  _prev: OrderActionState,
  formData: FormData,
): Promise<OrderActionState> {
  const parsed = transitionSchema.safeParse({
    order_id: String(formData.get("order_id") ?? ""),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) return { error: "Give a reason between 3 and 500 characters." };
  const rawReleaseAt = String(formData.get("release_at") ?? "").trim();
  let release_at: string | null = null;
  if (rawReleaseAt) {
    const date = new Date(rawReleaseAt);
    if (Number.isNaN(date.getTime())) return { error: "Enter a valid release date and time" };
    release_at = date.toISOString();
  }
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/payouts/correction-orders/{order_id}/approve", {
      params: { path: { order_id: parsed.data.order_id } },
      body: { release_at, reason: parsed.data.reason },
    });
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: error instanceof ApiError ? publicActionError(error) : "Could not reach the server.",
    };
  }
  revalidatePath("/admin/money");
  return { done: "Completed — pay changes recorded" };
}
