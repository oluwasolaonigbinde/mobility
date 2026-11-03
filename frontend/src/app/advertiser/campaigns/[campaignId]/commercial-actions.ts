"use server";

import { unstable_rethrow } from "next/navigation";

import { z } from "zod";
import { refresh } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { publicActionError } from "@/lib/api/public-action-error";
import { getSessionToken } from "@/lib/auth/session";

export interface CommercialActionState {
  error?: string;
  done?: string;
  acceptedTerms?: components["schemas"]["CommercialTermsRead"];
}

const commercialErrors = {
  QUOTE_REQUEST_ALREADY_EXISTS: "A quotation request already exists for this campaign.",
  QUOTATION_REVISION_SUPERSEDED: "A newer quotation is available. Review it before accepting.",
  COMMERCIAL_TERMS_ALREADY_ACCEPTED: "This quotation was already accepted.",
  QUOTATION_CURRENCY_MISMATCH: "The quotation currency no longer matches this campaign.",
  EXPEDITED_WAIVER_COPY_MISMATCH: "This wording has changed. Refresh and read it again.",
} as const;

const campaignCommandSchema = z.object({ campaignId: z.string().uuid() });
const quotationAcceptanceSchema = campaignCommandSchema.extend({
  revisionId: z.string().uuid(),
  confirmed: z.literal("on"),
});

function safeCommercialError(error: unknown, fallback: string) {
  return publicActionError(error, commercialErrors, fallback);
}

export async function requestQuoteAction(
  _previous: CommercialActionState,
  formData: FormData,
): Promise<CommercialActionState> {
  const parsed = campaignCommandSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
  });
  if (!parsed.success)
    return { error: "This quotation request is invalid. Refresh and try again." };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/quote-request", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body: {
        request_details: {
          notes: String(formData.get("notes") ?? "").trim(),
        },
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    return { error: safeCommercialError(error, "Could not request a quotation. Try again.") };
  }
  refresh();
  return { done: "Quotation requested. Terrax Media will post it here for review." };
}

export async function acceptQuoteAction(
  _previous: CommercialActionState,
  formData: FormData,
): Promise<CommercialActionState> {
  const parsed = quotationAcceptanceSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
    revisionId: String(formData.get("revision_id") ?? ""),
    confirmed: String(formData.get("confirmed") ?? ""),
  });
  if (!parsed.success) {
    return { error: "Review the quotation and confirm that you accept these exact terms." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/advertiser/quotations/{revision_id}/accept", {
      params: { path: { revision_id: parsed.data.revisionId } },
      body: { acceptance_method: "in_platform" },
    });
    if (!data) return { error: "Your accepted quotation can't be shown right now. Try again." };
    refresh();
    return {
      done: "Quotation accepted. Your accepted quotation is shown below.",
      acceptedTerms: data,
    };
  } catch (error) {
    unstable_rethrow(error);
    return { error: safeCommercialError(error, "Could not accept the quotation. Try again.") };
  }
}

export async function acceptExpeditedWaiverAction(
  _previous: CommercialActionState,
  formData: FormData,
): Promise<CommercialActionState> {
  const parsed = campaignCommandSchema.safeParse({
    campaignId: String(formData.get("campaign_id") ?? ""),
  });
  if (!parsed.success)
    return {
      error: "Your earlier-start request didn't go through. Refresh and try again.",
    };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/expedited-waiver", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body: {
        wording_version: String(formData.get("wording_version") ?? ""),
        accepted_wording: String(formData.get("accepted_wording") ?? ""),
        accepted_wording_hash: String(formData.get("accepted_wording_hash") ?? ""),
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    return {
      error: safeCommercialError(error, "Your earlier-start request didn't go through. Try again."),
    };
  }
  return { done: "Earlier production start agreed." };
}
