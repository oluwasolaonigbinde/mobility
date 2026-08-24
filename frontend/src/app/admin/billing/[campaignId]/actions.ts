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

export async function recordManualTransferAction(
  campaignId: string,
  organizationId: string,
  termsId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/billing/manual-transfers", {
      body: {
        organization_id: organizationId,
        commercial_terms_id: termsId,
        external_transaction_id: String(formData.get("external_transaction_id") ?? "").trim(),
        observed_amount: String(formData.get("observed_amount") ?? "").trim(),
        expected_amount: String(formData.get("expected_amount") ?? "").trim(),
        allocation_amount: String(formData.get("allocation_amount") ?? "").trim() || null,
        currency: String(formData.get("currency") ?? "").trim().toUpperCase(),
        payer_name: String(formData.get("payer_name") ?? "").trim(),
        evidence_reference: String(formData.get("evidence_reference") ?? "").trim(),
        observed_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=transfer`);
}

export async function createInvoiceAction(campaignId: string, termsId: string) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/invoices", { body: { commercial_terms_id: termsId } });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=invoice`);
}

export async function reverseReceiptAction(
  campaignId: string,
  receiptId: string,
  formData: FormData,
) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/receipts/{receipt_id}/reverse", {
      params: { path: { receipt_id: receiptId } },
      body: { reason: String(formData.get("reason") ?? "").trim() },
    });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=reversal`);
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
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=refund`);
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
        correction_type: String(formData.get("correction_type")) as "credit_note" | "debit_note",
        net_amount: String(formData.get("net_amount") ?? "").trim(),
        tax_amount: String(formData.get("tax_amount") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
      },
    });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=correction`);
}
