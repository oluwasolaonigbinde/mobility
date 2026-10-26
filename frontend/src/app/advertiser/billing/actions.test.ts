import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  redirect: vi.fn((destination: string) => {
    throw new Error(`redirect:${destination}`);
  }),
  session: vi.fn(async () => "session-token"),
}));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: mocks.redirect,
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.session }));

import { startInvoicePayment } from "./actions";

const INVOICE_ID = "00000000-0000-4000-8000-000000000001";

function paymentForm(invoiceId = INVOICE_ID): FormData {
  const form = new FormData();
  form.set("invoiceId", invoiceId);
  return form;
}

describe("startInvoicePayment", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.redirect.mockImplementation((destination: string) => {
      throw new Error(`redirect:${destination}`);
    });
  });

  it("rejects a malformed invoice before requesting a checkout", async () => {
    await expect(startInvoicePayment(paymentForm("not-an-invoice"))).rejects.toThrow(
      "redirect:/advertiser/billing?payment=error&message=Choose+a+valid+invoice.",
    );
    expect(mocks.post).not.toHaveBeenCalled();
    expect(mocks.session).not.toHaveBeenCalled();
  });

  it("opens the Paystack URL returned for the owned invoice", async () => {
    mocks.post.mockResolvedValueOnce({
      data: { checkout_url: "https://checkout.paystack.com/synthetic" },
    });

    await expect(startInvoicePayment(paymentForm())).rejects.toThrow(
      "redirect:https://checkout.paystack.com/synthetic",
    );
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/invoices/{invoice_id}/checkout", {
      params: { path: { invoice_id: INVOICE_ID } },
    });
  });

  it("keeps the advertiser on Cardvert when Paystack has no URL yet", async () => {
    mocks.post.mockResolvedValueOnce({ data: { checkout_url: null } });

    await expect(startInvoicePayment(paymentForm())).rejects.toThrow(
      "redirect:/advertiser/billing?payment=error&message=Paystack%20is%20still%20preparing%20this%20checkout.%20Please%20try%20again.",
    );
  });

  it.each(["confirmed", "failed"])(
    "shows reconciled %s status without reopening an old payment URL",
    async (status) => {
      mocks.post.mockResolvedValueOnce({
        data: { status, checkout_url: "https://checkout.paystack.com/old" },
      });
      await expect(startInvoicePayment(paymentForm())).rejects.toThrow(
        `redirect:/advertiser/billing?payment=${status}`,
      );
    },
  );

  it("uses a safe message when checkout creation fails", async () => {
    mocks.post.mockRejectedValueOnce(new Error("private upstream detail"));

    await expect(startInvoicePayment(paymentForm())).rejects.toThrow(
      "redirect:/advertiser/billing?payment=error&message=Cardvert%20could%20not%20open%20Paystack.%20Check%20your%20payment%20status%20before%20trying%20again.",
    );
  });
});
