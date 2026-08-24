"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

function campaignPath(campaignId: string) {
  return `/advertiser/campaigns/${campaignId}`;
}

export async function requestQuoteAction(campaignId: string, formData: FormData) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/quote-request", {
      params: { path: { campaign_id: campaignId } },
      body: {
        request_details: {
          notes: String(formData.get("notes") ?? "").trim(),
        },
      },
    });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Could not request a quotation";
    redirect(`${campaignPath(campaignId)}?commercial_error=${encodeURIComponent(message)}`);
  }
  revalidatePath(campaignPath(campaignId));
  redirect(`${campaignPath(campaignId)}?quote_requested=1`);
}

export async function acceptQuoteAction(campaignId: string, revisionId: string) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/quotations/{revision_id}/accept", {
      params: { path: { revision_id: revisionId } },
      body: { acceptance_method: "in_platform" },
    });
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Could not accept the quotation";
    redirect(`${campaignPath(campaignId)}?commercial_error=${encodeURIComponent(message)}`);
  }
  revalidatePath(campaignPath(campaignId));
  redirect(`${campaignPath(campaignId)}?quote_accepted=1`);
}
