"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

function path(campaignId: string) {
  return `/admin/campaigns/${campaignId}`;
}

function fail(campaignId: string, error: unknown): never {
  const message = error instanceof ApiError ? error.message : "The billing action failed";
  redirect(`${path(campaignId)}?error=${encodeURIComponent(message)}#money`);
}

export async function recordRevisionAction(
  campaignId: string,
  quoteRequestId: string,
  formData: FormData,
) {
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
        tax_rate: String(formData.get("tax_rate") ?? "").trim(),
      },
    });
  } catch (error) {
    fail(campaignId, error);
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
        currency: String(formData.get("currency") ?? "")
          .trim()
          .toUpperCase(),
        payer_name: String(formData.get("payer_name") ?? "").trim(),
        evidence_reference: String(formData.get("evidence_reference") ?? "").trim(),
        observed_at: new Date().toISOString(),
      },
    });
  } catch (error) {
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=transfer#money`);
}

export async function createInvoiceAction(campaignId: string, termsId: string) {
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/invoices", { body: { commercial_terms_id: termsId } });
  } catch (error) {
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
  redirect(`${path(campaignId)}?saved=reversal#money`);
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
        tax_amount: String(formData.get("tax_amount") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
      },
    });
  } catch (error) {
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
  try {
    const api = createApiClient(await getSessionToken());
    const isCredit = paymentClass === "approved_corporate_credit";
    await api.POST("/api/v1/admin/campaigns/{campaign_id}/financial-authority", {
      params: { path: { campaign_id: campaignId } },
      body: {
        authority_type: isCredit ? "approved_credit" : "prepaid_cash",
        max_driver_liability: String(formData.get("max_driver_liability") ?? "").trim(),
        reason: String(formData.get("reason") ?? "").trim(),
        credit_limit: isCredit ? String(formData.get("credit_limit") ?? "").trim() : null,
        due_at: isCredit ? new Date(String(formData.get("due_at") ?? "")).toISOString() : null,
        approved_by_user_id: isCredit ? approverId : null,
        credit_terms: isCredit
          ? { notes: String(formData.get("credit_terms") ?? "").trim() }
          : null,
      },
    });
  } catch (error) {
    if (error instanceof ApiError) {
      const messages: Record<string, string> = {
        FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE:
          "This approval cannot reduce the existing funding or maximum amount owed to drivers. Enter an amount at least as high as the current approval.",
        DRIVER_LIABILITY_EXCEEDS_AUTHORITY:
          "The maximum amount owed to drivers cannot exceed the approved funding.",
        INVALID_FINANCIAL_AUTHORITY_AMOUNT:
          "The approved funding and maximum amount owed to drivers must both be greater than zero.",
      };
      const message = messages[error.code];
      if (message) redirect(`${path(campaignId)}?error=${encodeURIComponent(message)}#money`);
    }
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
    fail(campaignId, error);
  }
  revalidatePath(path(campaignId));
  redirect(`${path(campaignId)}?saved=production#money`);
}
