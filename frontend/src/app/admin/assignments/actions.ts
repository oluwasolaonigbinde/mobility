"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface AdminActionState {
  error?: string;
}

const createSchema = z.object({
  campaign_id: z.string().uuid("Pick a campaign"),
  driver_profile_id: z.string().uuid("Pick a driver"),
  vehicle_id: z.string().uuid("Pick a vehicle"),
  notes: z
    .string()
    .trim()
    .max(500)
    .transform((v) => (v === "" ? null : v)),
});

export async function createAssignmentAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const parsed = createSchema.safeParse({
    campaign_id: formData.get("campaign_id"),
    driver_profile_id: formData.get("driver_profile_id"),
    vehicle_id: formData.get("vehicle_id"),
    notes: formData.get("notes") ?? "",
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments", { body: parsed.data });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/assignments");
  redirect("/admin/assignments");
}

export async function cancelAssignmentAction(assignmentId: string): Promise<AdminActionState> {
  if (!z.string().uuid().safeParse(assignmentId).success) return { error: "Invalid assignment" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments/{assignment_id}/cancel", {
      params: { path: { assignment_id: assignmentId } },
      body: {},
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/assignments");
  return {};
}
