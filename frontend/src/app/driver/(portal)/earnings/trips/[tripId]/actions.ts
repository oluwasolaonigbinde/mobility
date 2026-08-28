"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface FraudDisputeActionState {
  error?: string;
  done?: string;
}

const disputeSchema = z.object({
  flag_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  message: z.string().trim().min(1, "Tell us what you would like reviewed").max(2000),
});

export async function submitFraudDisputeAction(
  _prev: FraudDisputeActionState,
  formData: FormData,
): Promise<FraudDisputeActionState> {
  const parsed = disputeSchema.safeParse({
    flag_id: String(formData.get("flag_id") ?? ""),
    trip_id: String(formData.get("trip_id") ?? ""),
    message: String(formData.get("message") ?? ""),
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid dispute request" };
  }

  const { flag_id, trip_id, message } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/driver/fraud-holds/{flag_id}/disputes", {
      params: { path: { flag_id } },
      body: { message },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401 || error.status === 403) {
        return { error: "Your session is no longer valid. Sign in again before retrying." };
      }
      if (error.status === 409) {
        return { error: "A dispute already exists for this assessment. Refresh to see it." };
      }
      return { error: error.message };
    }
    return { error: "Could not reach the server." };
  }

  revalidatePath(`/driver/earnings/trips/${trip_id}`);
  return { done: "Your dispute was submitted for staff review." };
}
