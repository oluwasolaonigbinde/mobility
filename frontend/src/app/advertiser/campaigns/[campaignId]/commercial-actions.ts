"use server";

import { z } from "zod";
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
  COMMERCIAL_TERMS_ALREADY_ACCEPTED: "Commercial terms were already accepted for this campaign.",
  QUOTATION_CURRENCY_MISMATCH: "The quotation currency no longer matches this campaign.",
  EXPEDITED_WAIVER_COPY_MISMATCH: "The waiver wording changed. Refresh and review it again.",
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
    return { error: safeCommercialError(error, "Could not request a quotation. Try again.") };
  }
  return { done: "Quotation requested. Cardvert will post it here for review." };
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
    if (!data) return { error: "The accepted terms receipt is unavailable. Try again." };
    return {
      done: "Quotation accepted. Your immutable receipt is shown below.",
      acceptedTerms: data,
    };
  } catch (error) {
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
  if (!parsed.success) return { error: "This waiver request is invalid. Refresh and try again." };
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
    return { error: safeCommercialError(error, "Could not record the waiver. Try again.") };
  }
  return { done: "Expedited production waiver recorded." };
}
