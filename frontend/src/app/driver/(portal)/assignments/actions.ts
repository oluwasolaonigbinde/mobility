"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export async function assignmentAction({
  assignmentId,
  action,
}: {
  assignmentId: string;
  action: "accept" | "decline" | "deactivate";
}): Promise<{ error?: string }> {
  if (!z.string().uuid().safeParse(assignmentId).success) return { error: "Invalid assignment" };
  try {
    const api = createApiClient(await getSessionToken());
    if (action === "accept") {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/accept", {
        params: { path: { assignment_id: assignmentId } },
        body: {},
      });
    } else if (action === "decline") {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/decline", {
        params: { path: { assignment_id: assignmentId } },
        body: {},
      });
    } else {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/deactivate", {
        params: { path: { assignment_id: assignmentId } },
        body: {},
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/driver/assignments");
  return {};
}
