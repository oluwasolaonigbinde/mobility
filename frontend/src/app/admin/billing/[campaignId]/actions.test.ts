import { beforeEach, describe, expect, it, vi } from "vitest";

const { post, redirect, revalidatePath } = vi.hoisted(() => ({
  post: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
  revalidatePath: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect,
}));
vi.mock("next/cache", () => ({ revalidatePath }));

import {
  recordFinancialAuthorityAction,
  recordInvoiceCorrectionAction,
  recordManualTransferAction,
  recordRevisionAction,
  reverseReceiptAction,
  recordPaymentNotReceivedAction,
} from "./actions";
import { billingErrorCopy } from "./billing-errors";
import { ApiError } from "@/lib/api/errors";

describe("receipt reversal and payment not received", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    post.mockResolvedValue({ data: {} });
  });
  it.each(["refund", "not_received"])("sends the selected reversal kind %s", async (kind) => {
    const form = new FormData();
    form.set("kind", kind);
    form.set("reason", " Bank confirmation ");
    await expect(reverseReceiptAction("campaign-1", "receipt-1", form)).rejects.toThrow(
      "redirect:/admin/campaigns/campaign-1?saved=reversal#money",
    );
    expect(post).toHaveBeenCalledWith("/api/v1/admin/receipts/{receipt_id}/reverse", {
      params: { path: { receipt_id: "receipt-1" } },
      body: { kind, reason: "Bank confirmation" },
    });
    expect(revalidatePath).toHaveBeenCalledWith("/admin/campaigns/campaign-1");
  });
  it.each(["", "other"])("requires a valid explicit kind (%s)", async (kind) => {
    const form = new FormData();
    if (kind) form.set("kind", kind);
    await expect(reverseReceiptAction("campaign-1", "receipt-1", form)).rejects.toThrow(
      "?error=REVERSAL_KIND_REQUIRED#money",
    );
    expect(post).not.toHaveBeenCalled();
    expect(billingErrorCopy("REVERSAL_KIND_REQUIRED")).toBe(
      "Choose why you are reversing this payment.",
    );
  });
  it("marks a reversed payment not received through its receipt endpoint", async () => {
    const form = new FormData();
    form.set("reason", " Chargeback confirmed ");
    await expect(recordPaymentNotReceivedAction("campaign-1", "receipt-1", form)).rejects.toThrow(
      "redirect:/admin/campaigns/campaign-1?saved=not_received#money",
    );
    expect(post).toHaveBeenCalledWith("/api/v1/admin/receipts/{receipt_id}/not-received", {
      params: { path: { receipt_id: "receipt-1" } },
      body: { reason: "Chargeback confirmed" },
    });
    expect(revalidatePath).toHaveBeenCalledWith("/admin/campaigns/campaign-1");
  });
  it.each([
    ["CAMPAIGN_CANCELLED_NO_PAYMENT", "This cancelled campaign cannot accept any more payments."],
    ["REFUND_PAYMENT_NOT_RECEIVED", "This payment was not received, so it cannot be refunded."],
    ["REFUND_EXCEEDS_REFUND_STILL_DUE", "Enter a refund no larger than the refund still due."],
    ["RECEIPT_NOT_REVERSED", "Reverse this payment before marking it as not received."],
    ["NOT_RECEIVED_REASON_REQUIRED", "Enter a reason why the payment was not received."],
    [
      "RECEIPT_ALREADY_REVERSED",
      "This payment has already been reversed. Refresh the page to see its current status.",
    ],
    [
      "CANCELLATION_SNAPSHOT_INCOMPLETE",
      "The cancellation's payment records are incomplete. Ask the team to check them before continuing.",
    ],
  ])("redirects %s with friendly fixed copy", async (code, copy) => {
    post.mockRejectedValueOnce(new ApiError(409, { code, message: "private backend detail" }));
    await expect(
      recordPaymentNotReceivedAction("campaign-1", "receipt-1", new FormData()),
    ).rejects.toThrow(`redirect:/admin/campaigns/campaign-1?error=${code}#money`);
    expect(billingErrorCopy(code)).toBe(copy);
    expect(revalidatePath).not.toHaveBeenCalled();
  });
  it("keeps reversal API errors in the existing redirect pattern", async () => {
    post.mockRejectedValueOnce(
      new ApiError(409, { code: "RECEIPT_ALREADY_REVERSED", message: "private" }),
    );
    const form = new FormData();
    form.set("kind", "refund");
    await expect(reverseReceiptAction("campaign-1", "receipt-1", form)).rejects.toThrow(
      "?error=RECEIPT_ALREADY_REVERSED#money",
    );
    expect(revalidatePath).not.toHaveBeenCalled();
  });
});

describe("recordRevisionAction", () => {
  beforeEach(() => vi.clearAllMocks());
  it.each([
    ["7.5", "0.075"],
    ["0", "0"],
    ["100", "1"],
    ["0.0001", "0.000001"],
  ])("sends %s percent as the exact rate %s", async (percentage, rate) => {
    post.mockResolvedValue({ data: {} });
    const form = new FormData();
    form.set("tax_percentage", percentage);
    await expect(recordRevisionAction("campaign-1", "quote-1", form)).rejects.toThrow("redirect:");
    expect(post.mock.calls[0]![1].body.tax_rate).toBe(rate);
  });
  it.each(["101", "-1", "7.50000", "0.00001"])(
    "refuses invalid percentage %s before calling the API",
    async (percentage) => {
      const form = new FormData();
      form.set("tax_percentage", percentage);
      await expect(recordRevisionAction("campaign-1", "quote-1", form)).resolves.toEqual({
        error: "Enter VAT from 0 to 100%, with up to 4 decimal places.",
      });
      expect(post).not.toHaveBeenCalled();
    },
  );
  it("sends a quantity-priced line and the campaign dates to the quotation API", async () => {
    post.mockResolvedValue({ data: {} });
    const form = new FormData();
    form.set("quote_reference", " Q-1 ");
    form.set("description", "Mobile billboard campaign");
    form.set("quantity", "3");
    form.set("unit_amount", "100000.00");
    form.set("tax_percentage", "7.5");
    form.set("currency", "ngn");
    form.set("vehicle_count", "10");
    form.set("campaign_start_date", "2026-10-01");
    form.set("campaign_end_date", "2026-10-31");
    form.set("payment_class", "standard_prepaid");
    form.set("payment_terms", "Pay before printing");

    await expect(recordRevisionAction("campaign-1", "quote-1", form)).rejects.toThrow(
      "redirect:/admin/campaigns/campaign-1?saved=quotation#money",
    );
    expect(post).toHaveBeenCalledWith("/api/v1/admin/quote-requests/{quote_request_id}/revisions", {
      params: { path: { quote_request_id: "quote-1" } },
      body: {
        quote_reference: "Q-1",
        currency: "NGN",
        line_items: [
          {
            code: "MEDIA",
            description: "Mobile billboard campaign",
            kind: "media",
            quantity: 3,
            unit_amount: "100000.00",
          },
        ],
        production_scope: {
          vehicle_count: 10,
          campaign_start_date: "2026-10-01",
          campaign_end_date: "2026-10-31",
        },
        payment_class: "standard_prepaid",
        payment_terms: { notes: "Pay before printing" },
        tax_rate: "0.075",
      },
    });
  });

  it.each(["0", "25000.00"])(
    "keeps production as its own optional line (%s)",
    async (production) => {
      const form = new FormData();
      form.set("tax_percentage", "7.5");
      form.append("description", "Media");
      form.append("quantity", "2");
      form.append("unit_amount", "50000.00");
      form.append("line_code", "M");
      form.append("line_kind", "media");
      form.append("description", "Printing and fitting");
      form.append("quantity", "1");
      form.append("unit_amount", production);
      form.append("line_code", "P");
      form.append("line_kind", "production");
      await expect(recordRevisionAction("campaign-1", "quote-1", form)).rejects.toThrow(
        "redirect:",
      );
      const lines = post.mock.calls[0]![1].body.line_items;
      expect(lines).toHaveLength(production === "0" ? 1 : 2);
      if (production !== "0")
        expect(lines[1]).toMatchObject({
          kind: "production",
          quantity: 1,
          unit_amount: production,
        });
    },
  );
});
it.each([
  [
    "FINANCIAL_AUTHORITY_REDUCTION_REQUIRES_GOVERNANCE",
    "Package 3 permits funded expansions only; reductions require governed revision",
    "This approval cannot reduce the existing funding or maximum amount owed to drivers. Enter an amount at least as high as the current approval.",
  ],
  [
    "DRIVER_LIABILITY_EXCEEDS_AUTHORITY",
    "Maximum driver liability cannot exceed financial authority",
    "The maximum amount owed to drivers cannot exceed the approved funding.",
  ],
  [
    "INVALID_FINANCIAL_AUTHORITY_AMOUNT",
    "Authorized amount and maximum driver liability must be positive",
    "The approved funding and maximum amount owed to drivers must both be greater than zero.",
  ],
])("explains funding refusal %s without internal wording", async (code, raw, plain) => {
  post.mockRejectedValueOnce(new ApiError(409, { code, message: raw }));
  const form = new FormData();
  form.set("max_driver_liability", "40000");
  form.set("reason", "Synthetic approval check");
  // REQ-316 F10: the redirect carries the refusal code; the page maps it to fixed copy.
  await expect(
    recordFinancialAuthorityAction("campaign-1", "standard_prepaid", "admin-1", form),
  ).rejects.toThrow(`redirect:/admin/campaigns/campaign-1?error=${code}#money`);
  expect(billingErrorCopy(code)).toBe(plain);
});
it("submits a raised approval to the existing authority command", async () => {
  post.mockResolvedValueOnce({ data: {} });
  const form = new FormData();
  form.set("max_driver_liability", "60000.00");
  form.set("reason", "Raised approval for funded work");
  await expect(
    recordFinancialAuthorityAction("campaign-1", "standard_prepaid", "admin-1", form),
  ).rejects.toThrow("redirect:/admin/campaigns/campaign-1?saved=authority#money");
  expect(post).toHaveBeenLastCalledWith(
    "/api/v1/admin/campaigns/{campaign_id}/financial-authority",
    {
      params: { path: { campaign_id: "campaign-1" } },
      body: {
        authority_type: "prepaid_cash",
        max_driver_liability: "60000.00",
        reason: "Raised approval for funded work",
        credit_limit: null,
        due_at: null,
        approved_by_user_id: null,
        credit_terms: null,
      },
    },
  );
});
it("explains that a transfer needs an issued invoice", async () => {
  post.mockRejectedValueOnce(
    new ApiError(409, {
      code: "INVOICE_NOT_ISSUED",
      message: "Money can be recorded only against an issued invoice",
    }),
  );
  // REQ-316 F10: a code in the URL, fixed copy on the page.
  await expect(
    recordManualTransferAction("campaign-1", "org-1", "terms-1", new FormData()),
  ).rejects.toThrow("redirect:/admin/campaigns/campaign-1?error=INVOICE_NOT_ISSUED#money");
  expect(billingErrorCopy("INVOICE_NOT_ISSUED")).toBe(
    "Payments can be recorded once the invoice is issued.",
  );
});

describe("recordInvoiceCorrectionAction", () => {
  beforeEach(() => vi.clearAllMocks());
  it("sends only the net amount; the server derives VAT", async () => {
    post.mockResolvedValueOnce({ data: {} });
    const form = new FormData();
    form.set("correction_reference", "ref-1");
    form.set("correction_type", "credit_note");
    form.set("net_amount", " 100.00 ");
    form.set("tax_amount", "7.50");
    form.set("reason", " Scope reduced ");
    await expect(recordInvoiceCorrectionAction("campaign-1", "invoice-1", form)).rejects.toThrow(
      "redirect:/admin/campaigns/campaign-1?saved=correction#money",
    );
    expect(post).toHaveBeenCalledWith("/api/v1/admin/invoices/{invoice_id}/corrections", {
      params: { path: { invoice_id: "invoice-1" } },
      body: {
        correction_reference: "ref-1",
        correction_type: "credit_note",
        net_amount: "100.00",
        reason: "Scope reduced",
      },
    });
  });
  it.each([
    [
      "INVOICE_CREDIT_BELOW_FUNDED",
      "This credit note would take the invoice below the money already received. Credit a smaller amount, or record a refund instead.",
    ],
    [
      "INVOICE_CORRECTION_VAT_INCONSISTENT",
      "Earlier corrections on this invoice don't match its VAT rate, so another correction can't be added. Ask the team to check this invoice.",
    ],
    [
      "INVOICE_CREDIT_EXCEEDS_OBLIGATION",
      "A credit note can't be larger than the amount still on the invoice.",
    ],
  ])("redirects refusal %s as a code with plain copy", async (code, plain) => {
    post.mockRejectedValueOnce(new ApiError(409, { code, message: "raw backend text" }));
    const form = new FormData();
    form.set("correction_type", "credit_note");
    await expect(recordInvoiceCorrectionAction("campaign-1", "invoice-1", form)).rejects.toThrow(
      `redirect:/admin/campaigns/campaign-1?error=${code}#money`,
    );
    expect(billingErrorCopy(code)).toBe(plain);
  });
});

describe("billingErrorCopy", () => {
  it("never echoes URL text", () => {
    expect(billingErrorCopy("Your account is locked, call 0800")).toBe(
      "That didn't work. Please try again.",
    );
    expect(billingErrorCopy("failed")).toBe("That didn't work. Please try again.");
    expect(billingErrorCopy("toString")).toBe("That didn't work. Please try again.");
    expect(billingErrorCopy(undefined)).toBeNull();
  });
});

describe("billing failure copy does not claim money was recorded", () => {
  beforeEach(() => vi.resetAllMocks());
  it.each([true, false])("keeps failed quotation edits on the form (API %s)", async (api) => {
    post.mockRejectedValue(
      api ? new ApiError(422, { code: "BAD_QUOTE", message: "raw SQL" }) : new Error("offline"),
    );
    const form = new FormData();
    form.set("tax_percentage", "0");
    expect(await recordRevisionAction("campaign-1", "quote-1", form)).toEqual({
      error: api
        ? "That didn't work. Please try again."
        : "The quotation could not be saved. Try again.",
    });
    expect(revalidatePath).not.toHaveBeenCalled();
    expect(redirect).not.toHaveBeenCalled();
  });
  it.each([true, false])(
    "redirects failed transfers with fixed refusal copy (API %s)",
    async (api) => {
      post.mockRejectedValue(
        api
          ? new ApiError(409, { code: "INVOICE_NOT_ISSUED", message: "raw amount" })
          : new Error("offline"),
      );
      await expect(
        recordManualTransferAction("campaign-1", "org-1", "terms-1", new FormData()),
      ).rejects.toThrow("redirect:");
      // REQ-316 F10: codes, not copy, travel in the URL.
      const code = api ? "INVOICE_NOT_ISSUED" : "failed";
      expect(redirect).toHaveBeenCalledWith(`/admin/campaigns/campaign-1?error=${code}#money`);
      expect(revalidatePath).not.toHaveBeenCalled();
    },
  );
});
