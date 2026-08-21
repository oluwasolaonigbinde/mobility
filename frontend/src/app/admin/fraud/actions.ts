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

const reviewSchema = z.discriminatedUnion("intent", [
  z.object({
    flag_id: z.string().uuid(),
    intent: z.literal("acknowledge"),
  }),
  z.object({
    flag_id: z.string().uuid(),
    intent: z.enum(["confirm", "dismiss"]),
    note: z.string().trim().min(1, "A review note is required").max(2000),
  }),
]);

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
    if (intent === "acknowledge") {
      await api.POST("/api/v1/admin/fraud-flags/{flag_id}/review/acknowledge", path);
    } else {
      await api.POST("/api/v1/admin/fraud-flags/{flag_id}/review/resolve", {
        ...path,
        body: {
          outcome: intent === "confirm" ? "confirmed" : "dismissed",
          note: parsed.data.note,
        },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }

  revalidatePath("/admin/fraud");
  return {
    done:
      intent === "acknowledge"
        ? "Review acknowledged"
        : intent === "confirm"
          ? "Fraud confirmed"
          : "Flag dismissed",
  };
}
