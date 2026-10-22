"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface FraudReviewActionState {
  error?: string;
  done?: string;
}

export interface FraudDisputeReplyActionState {
  error?: string;
  done?: string;
}

export interface SpotCheckActionState {
  error?: string;
  done?: string;
}

const reviewSchema = z.object({
  flag_id: z.string().uuid(),
  intent: z.enum(["confirm", "dismiss"]),
  note: z.string().trim().min(1, "A review note is required").max(2000),
});

const disputeReplySchema = z.object({
  dispute_id: z.string().uuid(),
  reply: z.string().trim().min(1, "A driver reply is required").max(2000),
});

const spotCheckSchema = z.object({
  assignment_id: z.string().uuid(),
  trip_session_id: z.string().uuid(),
  client_request_id: z.string().uuid(),
  outcome: z.enum(["passed", "failed"]),
  note: z.string().trim().min(1, "A result note is required").max(2000),
});
export async function reviewFraudFlagAction(
  _prev: FraudReviewActionState,
  formData: FormData,
): Promise<FraudReviewActionState> {
  const parsed = reviewSchema.safeParse({
    flag_id: String(formData.get("flag_id") ?? ""),
    intent: String(formData.get("intent") ?? ""),
    note: String(formData.get("note") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid review request" };
  }

  const { flag_id, intent } = parsed.data;
  const api = createApiClient(await getSessionToken());
  const path = { params: { path: { flag_id } } };

  try {
    await api.POST("/api/v1/admin/fraud-flags/{flag_id}/review/resolve", {
      ...path,
      body: {
        outcome: intent === "confirm" ? "confirmed" : "dismissed",
        note: parsed.data.note,
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  revalidatePath("/admin/trip-checks");
  return {
    done: intent === "confirm" ? "Problem confirmed" : "Trip cleared",
  };
}

export async function replyFraudDisputeAction(
  _prev: FraudDisputeReplyActionState,
  formData: FormData,
): Promise<FraudDisputeReplyActionState> {
  const parsed = disputeReplySchema.safeParse({
    dispute_id: String(formData.get("dispute_id") ?? ""),
    reply: String(formData.get("reply") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid dispute reply" };
  }

  const { dispute_id, reply } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/fraud-disputes/{dispute_id}/reply", {
      params: { path: { dispute_id } },
      body: { reply },
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  revalidatePath("/admin/trip-checks");
  return { done: "Reply sent to driver" };
}

export async function recordSpotCheckAction(
  _prev: SpotCheckActionState,
  formData: FormData,
): Promise<SpotCheckActionState> {
  const parsed = spotCheckSchema.safeParse(
    Object.fromEntries(
      ["assignment_id", "trip_session_id", "client_request_id", "outcome", "note"].map((name) => [
        name,
        String(formData.get(name) ?? ""),
      ]),
    ),
  );
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the result" };
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/evidence-verifications/physical-spot-checks", {
      body: parsed.data,
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "The result couldn't be confirmed. Retry with the same details." };
  }
  revalidatePath("/admin/trip-checks");
  return {
    done:
      parsed.data.outcome === "passed" ? "In-person check passed" : "Failure sent to trip review",
  };
}
