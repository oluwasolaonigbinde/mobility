"use server";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
export async function resumeCampaign(_previous: { error?: string; done?: string }, form: FormData) {
  await requireRole("admin");
  const parsed = z
    .object({
      campaign_id: z.string().uuid(),
      reason: z.string().trim().min(1).max(1000),
      pause_id: z.string().uuid().optional(),
    })
    .safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: "Give a reason for resuming the campaign." };
  try {
    const api = createApiClient(await getSessionToken());
    if (parsed.data.pause_id) {
      await api.POST("/api/v1/admin/campaigns/{campaign_id}/resume", {
        params: { path: { campaign_id: parsed.data.campaign_id } },
        body: { reason: parsed.data.reason, pause_id: parsed.data.pause_id },
      });
    } else
      await api.POST("/api/v1/admin/campaigns/{campaign_id}/budget-policy-resume", {
        params: { path: { campaign_id: parsed.data.campaign_id } },
        body: { reason: parsed.data.reason },
      });
  } catch (error) {
    return { error: error instanceof ApiError ? error.message : "Could not reach the server." };
  }
  revalidatePath(`/admin/campaigns/${parsed.data.campaign_id}`);
  return { done: "Campaign resumed" };
}
