"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import {
  campaignWizardSchema,
  toApiDatetime,
  type CampaignWizardInput,
} from "@/lib/campaigns/schema";

export interface CreateCampaignState {
  error?: string;
  /** Set when the campaign was created but a creative failed — the UI links to it. */
  createdCampaignId?: string;
}

export async function createCampaignAction(
  input: CampaignWizardInput,
): Promise<CreateCampaignState> {
  // Server-side re-validation — the client schema is UX, this is the gate.
  const parsed = campaignWizardSchema.safeParse(input);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return { error: first ? `${first.path.join(".")}: ${first.message}` : "Invalid form data." };
  }
  const { basics, creatives } = parsed.data;

  const api = createApiClient(await getSessionToken());

  let campaignId: string;
  try {
    const { data } = await api.POST("/api/v1/advertiser/campaigns", {
      body: {
        name: basics.name,
        description: basics.description ?? null,
        status: "draft",
        start_at: toApiDatetime(basics.start_at) ?? null,
        end_at: toApiDatetime(basics.end_at) ?? null,
        budget_amount: basics.budget_amount ?? null,
        daily_budget_amount: basics.daily_budget_amount ?? null,
      },
    });
    if (!data) return { error: "Unexpected empty response creating the campaign." };
    campaignId = data.id;
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server. Please try again." };
  }

  for (const [index, creative] of creatives.entries()) {
    try {
      await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/creatives", {
        params: { path: { campaign_id: campaignId } },
        body: {
          name: creative.name,
          creative_type: creative.creative_type,
          placement: creative.placement,
          asset_url: creative.asset_url ?? null,
          status: "draft",
        },
      });
    } catch (error) {
      // Campaign exists; be honest about exactly what failed.
      const reason = error instanceof ApiError ? error.message : "server unreachable";
      return {
        error: `Campaign created, but creative ${index + 1} ("${creative.name}") failed: ${reason}`,
        createdCampaignId: campaignId,
      };
    }
  }

  revalidatePath("/advertiser/campaigns");
  redirect(`/advertiser/campaigns/${campaignId}`);
}
