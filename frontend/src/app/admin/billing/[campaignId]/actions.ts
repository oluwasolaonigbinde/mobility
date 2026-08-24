"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

function path(campaignId: string) {
  return `/admin/billing/${campaignId}`;
}

function fail(campaignId: string, error: unknown): never {
  const message = error instanceof ApiError ? error.message : "The billing action failed";
  redirect(`${path(campaignId)}?error=${encodeURIComponent(message)}`);
}

export async function recordRevisionAction(
  campaignId: string,
  quoteRequestId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/quote-requests/{quote_request_id}/revisions", {
      params: { path: { quote_request_id: quoteRequestId } },
      body: {
        quote_reference: String(formData.get("quote_reference") ?? "").trim(),
        currency: String(formData.get("currency") ?? "").trim().toUpperCase(),
        line_items: [
          {
            code: "MEDIA",
            description: String(formData.get("description") ?? "").trim(),
            kind: "media",
            amount: String(formData.get("amount") ?? "").trim(),
          },
        ],
        production_scope: {
          vehicle_count: Number(formData.get("vehicle_count") ?? 0),
        },
        payment_class: String(formData.get("payment_class")) as
          | "standard_prepaid"
          | "approved_corporate_credit",
        payment_terms: { notes: String(formData.get("payment_terms") ?? "").trim() },
        tax_rate: String(formData.get("tax_rate") ?? "").trim(),
      },
    });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=quotation`);
}
