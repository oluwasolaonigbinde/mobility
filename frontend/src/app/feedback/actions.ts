"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";
import { createApiClient } from "@/lib/api/client";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function setFeedbackStatusAction(formData: FormData): Promise<void> {
  const id = formData.get("id");
  const status = formData.get("status");
  if (typeof id !== "string" || !UUID.test(id) || (status !== "opened" && status !== "resolved"))
    return;
  try {
    await createApiClient().PATCH("/api/v1/feedback/{feedback_id}/status", {
      params: { path: { feedback_id: id } },
      body: { status },
    });
  } catch (error) {
    unstable_rethrow(error);
    // Unknown id or a passing outage: the refreshed list shows the current state.
  }
  revalidatePath("/feedback");
}
