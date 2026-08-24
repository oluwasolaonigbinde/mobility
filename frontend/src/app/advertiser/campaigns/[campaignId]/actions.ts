"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { CAMPAIGN_STATUSES } from "@/lib/campaigns/status";

const transitionSchema = z.object({
  campaignId: z.string().uuid(),
  to: z.enum(CAMPAIGN_STATUSES),
});

export interface TransitionState {
  error?: string;
}

export async function updateCampaignStatusAction(
  input: z.input<typeof transitionSchema>,
): Promise<TransitionState> {
  const parsed = transitionSchema.safeParse(input);
  if (!parsed.success) {
    return { error: "Invalid status transition request." };
  }

  try {
    const api = createApiClient(await getSessionToken());
    if (parsed.data.to === "active") {
      const { data: commercial } = await api.GET(
        "/api/v1/advertiser/campaigns/{campaign_id}/commercial",
        { params: { path: { campaign_id: parsed.data.campaignId } } },
      );
      if (commercial?.terms && !commercial.production_start) {
        return { error: "Funding and production authority are required before launch or resume." };
      }
    }
    await api.PATCH("/api/v1/advertiser/campaigns/{campaign_id}", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body: { status: parsed.data.to },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      return { error: error.message };
    }
    return { error: "Could not reach the server. Please try again." };
  }

  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}`);
  revalidatePath("/advertiser/campaigns");
  return {};
}
