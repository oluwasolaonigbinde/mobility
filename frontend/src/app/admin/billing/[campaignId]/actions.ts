"use server";

import { lagosLocalToApi } from "@/lib/campaigns/schema";
import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { vatPercentageToRate, VAT_PERCENTAGE_ERROR } from "@/lib/billing/vat-percentage";
import { BILLING_ERROR_COPY, billingErrorCode } from "./billing-errors";

function path(campaignId: string) {
  return `/admin/campaigns/${campaignId}`;
}

function fail(campaignId: string, error: unknown): never {
  // Never log backend text/details or submitted values; the URL carries only a code.
  console.warn("Cardvert action failed", {
    status: error instanceof ApiError ? error.status : "unavailable",
  });
  redirect(`${path(campaignId)}?error=${billingErrorCode(error)}#money`);
}

export async function recordRevisionAction(
  campaignId: string,
  quoteRequestId: string,
  formData: FormData,
) {
  const taxRate = vatPercentageToRate(String(formData.get("tax_percentage") ?? ""));
  if (taxRate === null) return { error: VAT_PERCENTAGE_ERROR };
  try {
    const api = createApiClient(await getSessionToken());
    const descriptions = formData.getAll("description");
    const quantities = formData.getAll("quantity");
    const amounts = formData.getAll("unit_amount");
    const codes = formData.getAll("line_code");
    const kinds = formData.getAll("line_kind");
    const metadata = formData.getAll("line_metadata");
    const lineItems = descriptions
      .map((description, index) => ({
        code: String(codes[index] ?? "MEDIA"),
        description: String(description).trim(),
        kind: String(kinds[index] ?? "media"),
        quantity: Number(quantities[index] ?? 0),
        unit_amount: String(amounts[index] ?? "").trim(),
        ...(metadata[index] ? { metadata: JSON.parse(String(metadata[index])) } : {}),
      }))
      .filter((line) => line.kind !== "production" || Number(line.unit_amount) !== 0);
    await api.POST("/api/v1/admin/quote-requests/{quote_request_id}/revisions", {
      params: { path: { quote_request_id: quoteRequestId } },
      body: {
        quote_reference: String(formData.get("quote_reference") ?? "").trim(),
        currency: String(formData.get("currency") ?? "")
          .trim()
          .toUpperCase(),
        line_items: lineItems,
        production_scope: {
          ...JSON.parse(String(formData.get("previous_production_scope") ?? "{}")),
          vehicle_count: Number(formData.get("vehicle_count") ?? 0),
          campaign_start_date: String(formData.get("campaign_start_date") ?? "").trim(),
          campaign_end_date: String(formData.get("campaign_end_date") ?? "").trim(),
        },
        payment_class: String(formData.get("payment_class")) as
          "standard_prepaid" | "approved_corporate_credit",
        payment_terms: {
          ...JSON.parse(String(formData.get("previous_payment_terms") ?? "{}")),
          notes: String(formData.get("payment_terms") ?? "").trim(),
        },
        tax_rate: taxRate,
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    return {
      error:
        error instanceof ApiError
          ? publicActionError(error, BILLING_ERROR_COPY)
          : "The quotation could not be saved. Try again.",
    };
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=quotation#money`);
}

export async function recordManualTransferAction(
  campaignId: string,
  organizationId: string,
  termsId: string,
  formData: FormData,
) {
  let matched: boolean | undefined;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/admin/billing/manual-transfers", {
      body: {
        organization_id: organizationId,
        commercial_terms_id: termsId,
        external_transaction_id: String(formData.get("external_transaction_id") ?? "").trim(),
        observed_amount: String(formData.get("observed_amount") ?? "").trim(),
        expected_amount: String(formData.get("expected_amount") ?? "").trim(),
        allocation_amount: String(formData.get("allocation_amount") ?? "").trim() || null,
        currency: String(formData.get("currency") ?? "")
          .trim()
          .toUpperCase(),
        payer_name: String(formData.get("payer_name") ?? "").trim(),
        evidence_reference: String(formData.get("evidence_reference") ?? "").trim(),
        observed_at: new Date().toISOString(),
      },
    });
    matched = data?.matched;
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  // A mismatched amount is recorded but not applied; an unreadable result is never shown as applied.
  const saved =
    matched === true ? "transfer" : matched === false ? "transfer_unmatched" : "transfer_unknown";
  redirect(`${path(campaignId)}?saved=${saved}#money`);
}

export async function createInvoiceAction(campaignId: string, termsId: string) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/invoices", { body: { commercial_terms_id: termsId } });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=invoice#money`);
}

export async function issueInvoiceAction(campaignId: string, invoiceId: string) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/invoices/{invoice_id}/issue", {
      params: { path: { invoice_id: invoiceId } },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=issued#money`);
}

export async function reverseReceiptAction(
  campaignId: string,
  receiptId: string,
  formData: FormData,
) {
  const kind = formData.get("kind");
  if (kind !== "refund" && kind !== "not_received") {
    redirect(`${path(campaignId)}?error=REVERSAL_KIND_REQUIRED#money`);
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/receipts/{receipt_id}/reverse", {
      params: { path: { receipt_id: receiptId } },
      body: { kind, reason: String(formData.get("reason") ?? "").trim() },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=reversal#money`);
}

export async function recordPaymentNotReceivedAction(
  campaignId: string,
  receiptId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/receipts/{receipt_id}/not-received", {
      params: { path: { receipt_id: receiptId } },
      body: { reason: String(formData.get("reason") ?? "").trim() },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=not_received#money`);
}

export async function recordRefundAction(
  campaignId: string,
  termsId: string,
  receiptId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/refunds", {
      body: {
        commercial_terms_id: termsId,
        receipt_id: receiptId,
        amount: String(formData.get("amount") ?? "").trim(),
        settlement_provider: String(formData.get("settlement_provider") ?? "").trim(),
        external_reference: String(formData.get("external_reference") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=refund#money`);
}

export async function recordInvoiceCorrectionAction(
  campaignId: string,
  invoiceId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/invoices/{invoice_id}/corrections", {
      params: { path: { invoice_id: invoiceId } },
      body: {
        correction_reference: String(formData.get("correction_reference") ?? "").trim(),
        correction_type: String(formData.get("correction_type")) as "credit_note" | "debit_note",
        net_amount: String(formData.get("net_amount") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=correction#money`);
}

export async function recordFinancialAuthorityAction(
  campaignId: string,
  paymentClass: "standard_prepaid" | "approved_corporate_credit",
  approverId: string,
  formData: FormData,
) {
  const isCredit = paymentClass === "approved_corporate_credit";
  const dueAt = isCredit ? lagosLocalToApi(String(formData.get("due_at") ?? "")) : null;
  if (isCredit && !dueAt) redirect(`${path(campaignId)}?error=INVALID_CREDIT_DUE_AT#money`);
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaigns/{campaign_id}/financial-authority", {
      params: { path: { campaign_id: campaignId } },
      body: {
        authority_type: isCredit ? "approved_credit" : "prepaid_cash",
        max_driver_liability: String(formData.get("max_driver_liability") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
        credit_limit: isCredit ? String(formData.get("credit_limit") ?? "").trim() : null,
        due_at: dueAt,
        approved_by_user_id: isCredit ? approverId : null,
        credit_terms: isCredit
          ? { notes: String(formData.get("credit_terms") ?? "").trim() }
          : null,
      },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=authority#money`);
}

export async function recordProductionStartAction(campaignId: string, waiverId: string | null) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaigns/{campaign_id}/production-start", {
      params: { path: { campaign_id: campaignId } },
      body: { waiver_id: waiverId },
    });
  } catch (error) {
    unstable_rethrow(error);
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=production#money`);
}
