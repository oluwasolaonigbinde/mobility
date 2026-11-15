import { ApiError } from "@/lib/api/errors";

// Billing refusals reach the page as a code in the URL; only this fixed copy is shown.
export const BILLING_ERROR_COPY = {
  CAMPAIGN_CANCELLED_NO_PAYMENT: "This cancelled campaign cannot accept any more payments.",
  REFUND_PAYMENT_NOT_RECEIVED: "This payment was not received, so it cannot be refunded.",
  REFUND_EXCEEDS_REFUND_STILL_DUE: "Enter a refund no larger than the refund still due.",
  REFUND_RECEIPT_NOT_COUNTED:
    "This payment didn't count towards the cancellation's refund, so it can't be refunded under it.",
  REFUND_EXCEEDS_COUNTED_PAYMENT:
    "Enter a refund no larger than what this payment counted towards the refund.",
  RECEIPT_NOT_REVERSED: "Reverse this payment before marking it as not received.",
  NOT_RECEIVED_REASON_REQUIRED: "Enter a reason why the payment was not received.",
  RECEIPT_ALREADY_REVERSED:
    "This payment has already been reversed. Refresh the page to see its current status.",
  CANCELLATION_SNAPSHOT_INCOMPLETE:
    "The cancellation's payment records are incomplete. Ask the team to check them before continuing.",
  REVERSAL_KIND_REQUIRED: "Choose why you are reversing this payment.",
  INVOICE_NOT_ISSUED: "Payments can be recorded once the invoice is issued.",
  QUOTE_REFERENCE_CONFLICT: "This quote reference is already used. Enter a different reference.",
  FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE:
    "This approval cannot reduce the existing funding or maximum amount owed to drivers. Enter an amount at least as high as the current approval.",
  DRIVER_LIABILITY_EXCEEDS_AUTHORITY:
    "The maximum amount owed to drivers cannot exceed the approved funding.",
  INVALID_FINANCIAL_AUTHORITY_AMOUNT:
    "The approved funding and maximum amount owed to drivers must both be greater than zero.",
  INVOICE_CREDIT_EXCEEDS_OBLIGATION:
    "A credit note can't be larger than the amount still on the invoice.",
  INVOICE_CREDIT_BELOW_FUNDED:
    "This credit note would take the invoice below the money already received. Credit a smaller amount, or record a refund instead.",
  INVOICE_CORRECTION_VAT_INCONSISTENT:
    "Earlier corrections on this invoice don't match its VAT rate, so another correction can't be added. Ask the team to check this invoice.",
  TRY_AGAIN_SOON: "This page is busy. Try again in a moment.",
} as const;

export type BillingErrorCode = keyof typeof BILLING_ERROR_COPY;

const FALLBACK = "That didn't work. Please try again.";

function isBillingErrorCode(code: string): code is BillingErrorCode {
  return Object.hasOwn(BILLING_ERROR_COPY, code);
}

/** The code to put in the redirect: a known refusal, otherwise a generic failure. */
export function billingErrorCode(error: unknown): BillingErrorCode | "failed" {
  return error instanceof ApiError && isBillingErrorCode(error.code) ? error.code : "failed";
}

/** Fixed copy for a code from the URL; unknown values never echo back. */
export function billingErrorCopy(code: string | undefined): string | null {
  if (!code) return null;
  return isBillingErrorCode(code) ? BILLING_ERROR_COPY[code] : FALLBACK;
}
