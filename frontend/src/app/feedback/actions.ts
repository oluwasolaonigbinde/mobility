"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { createFeedbackReviewApiClient, createLoginApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { loginClientIpHeader } from "@/lib/auth/client-ip";
import { env } from "@/lib/env";
import { clearReviewToken, getReviewToken, setReviewToken } from "./review-cookie";

export interface UnlockState {
  error?: string;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function unlockFeedbackAction(
  _previous: UnlockState,
  formData: FormData,
): Promise<UnlockState> {
  const password = formData.get("password");
  if (typeof password !== "string" || !password) return { error: "Enter the password." };
  try {
    const ip = loginClientIpHeader(await headers(), env().LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER);
    const { data } = await createLoginApiClient(ip).POST("/api/v1/feedback/review/unlock", {
      body: { password: password.slice(0, 1024) },
    });
    if (!data) throw new Error("Unlock unavailable");
    await setReviewToken(data.token, data.expires_at);
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) {
      if (error.status === 401) return { error: "That password did not match." };
      if (error.status === 429) return { error: "Too many attempts. Try again in a few minutes." };
      if (error.status === 404) return { error: "Feedback isn't switched on for this site." };
    }
    return { error: "Feedback is unavailable right now. Try again." };
  }
  redirect("/feedback");
}

export async function setFeedbackStatusAction(formData: FormData): Promise<void> {
  const id = formData.get("id");
  const status = formData.get("status");
  if (typeof id !== "string" || !UUID.test(id) || (status !== "opened" && status !== "resolved"))
    return;
  const token = await getReviewToken();
  if (!token) redirect("/feedback");
  try {
    await createFeedbackReviewApiClient(token).PATCH("/api/v1/feedback/{feedback_id}/status", {
      params: { path: { feedback_id: id } },
      body: { status },
    });
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && error.status === 401) {
      await clearReviewToken();
      redirect("/feedback");
    }
    // Unknown id or a passing outage: the refreshed list shows the current state.
  }
  revalidatePath("/feedback");
}
