import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, post, redirect, revalidatePath } = vi.hoisted(() => ({
  get: vi.fn(),
  // Only the real transfer action in the flow test posts; it fails closed by default.
  post: vi.fn<(path: string, init?: unknown) => Promise<unknown>>(async () => {
    throw new Error("unmocked POST");
  }),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
  revalidatePath: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get, POST: post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({ user: { id: "admin-1" } }),
}));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  notFound: vi.fn(),
  redirect,
}));
vi.mock("next/cache", () => ({ revalidatePath }));
vi.mock("./actions", () => ({
  createInvoiceAction: vi.fn(),
  issueInvoiceAction: vi.fn(),
  recordBudgetBlockedStateAction: vi.fn(),
  recordFinancialAuthorityAction: vi.fn(),
  recordInvoiceCorrectionAction: vi.fn(),
  recordManualTransferAction: vi.fn(),
  recordProductionStartAction: vi.fn(),
  recordRefundAction: vi.fn(),
  recordRevisionAction: vi.fn(),
  reverseReceiptAction: vi.fn(),
  recordPaymentNotReceivedAction: vi.fn(),
}));

import AdminCampaignBillingPage from "./content";

describe("receipt payment status controls", () => {
  it.each([
    ["confirmed", false],
    ["reversed", false],
    ["reversed", true],
  ])("shows appropriate controls for %s, not received %s", async (status, notReceived) => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/commercial")) return { data: commercial };
      if (path === "/api/v1/admin/billing")
        return {
          data: [
            {
              receipt: {
                id: "receipt-1",
                external_transaction_id: "TRF-1",
                amount: "100.00",
                currency: "NGN",
              },
              allocations: [{ commercial_terms_id: "terms-1" }],
              current_status: status,
              not_received: notReceived,
              not_received_reason: notReceived ? "Bank took back the transfer" : null,
              owed_back_amount: "0.00",
            },
          ],
        };
      return { data: campaign };
    });
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    const radios = screen.queryAllByRole("radio");
    expect(radios).toHaveLength(status === "confirmed" ? 2 : 0);
    if (status === "confirmed") {
      expect(screen.getByRole("radio", { name: "Returning it to the advertiser" })).toHaveAttribute(
        "value",
        "refund",
      );
      expect(
        screen.getByRole("radio", { name: "Money never arrived or was taken back" }),
      ).toHaveAttribute("value", "not_received");
      for (const radio of radios) {
        expect(radio).toBeRequired();
        expect(radio).not.toBeChecked();
      }
    }
    const canMark = status === "reversed" && !notReceived;
    expect(Boolean(screen.queryByRole("button", { name: "Payment not received" }))).toBe(canMark);
    expect(Boolean(screen.queryByRole("button", { name: "Record refund" }))).toBe(canMark);
    if (canMark) expect(screen.getByLabelText("Why was the payment not received?")).toBeRequired();
    // Both staff reason fields warn that the advertiser reads the reason.
    expect(screen.queryAllByText("The advertiser sees this reason.")).toHaveLength(
      status === "confirmed" || canMark ? 1 : 0,
    );
    if (notReceived)
      expect(screen.getByText("Payment not received: Bank took back the transfer")).toBeVisible();
  });
});

const campaign = {
  id: "campaign-1",
  name: "October launch",
  currency: "NGN",
  // 23:00 UTC on 30 September is 1 October in Nigeria.
  start_at: "2026-09-30T23:00:00Z",
  end_at: "2026-10-31T22:59:59Z",
  organization: { id: "org-1", name: "Acme Foods Ltd" },
};

const commercial = {
  quote_request: { id: "quote-1" },
  revisions: [],
  terms: {
    id: "terms-1",
    gross_amount: "107500.00",
    currency: "NGN",
    acceptance_method: "in_platform",
    standard_production_wait_hours: 24,
    payment_class: "standard_prepaid",
  },
  invoices: [
    {
      id: "invoice-1",
      status: "draft",
      invoice_number: null,
      currency: "NGN",
      net_amount: "100000.00",
      tax_amount: "7500.00",
      gross_amount: "107500.00",
      effective_obligation_amount: "107500.00",
      funded_amount: "0.00",
      payment_status: "unpaid",
      corrections: [],
    },
  ],
  settlements: [],
  unapplied_receipts: [] as unknown[],
  financial_authority: null,
  production_start: null,
  waiver: null,
};

describe("online payments not applied after a cancellation", () => {
  it("lists them, offers the reversal while unreturned and shows returned ones", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/commercial"))
        return {
          data: {
            ...commercial,
            unapplied_receipts: [
              {
                receipt_id: "late-1",
                amount: "25.00",
                currency: "NGN",
                observed_at: "2026-11-10T09:00:00Z",
                status: "confirmed",
              },
              {
                receipt_id: "late-2",
                amount: "40.00",
                currency: "NGN",
                observed_at: "2026-11-11T09:00:00Z",
                status: "reversed",
              },
            ],
          },
        };
      if (path === "/api/v1/admin/billing") return { data: [] };
      return { data: campaign };
    });
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Online payments not applied to this campaign" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "These online payments weren't applied to the campaign. Return each one to the advertiser outside Cardvert (for example a Paystack refund), then reverse it here as 'Returning it to the advertiser'.",
      ),
    ).toBeVisible();
    expect(screen.getByText("₦25.00")).toBeVisible();
    expect(screen.getByText("Not returned yet")).toBeVisible();
    expect(screen.getByText("Closed")).toBeVisible();
    // Only the unreturned payment gets the reversal form.
    expect(screen.getAllByRole("button", { name: "Record reversal" })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "Returning it to the advertiser" })).toHaveAttribute(
      "value",
      "refund",
    );
    expect(screen.getByPlaceholderText("Reversal reason")).toHaveAttribute("maxlength", "1000");
    expect(screen.getByText("The advertiser sees this reason.")).toBeVisible();
  });

  it("shows no section when nothing arrived after the cancellation", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? { data: commercial }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.queryByText("Online payments not applied to this campaign")).toBeNull();
  });
});

describe("admin campaign billing page", () => {
  it.each(["107500.00", "50000.00"])("shows the true balance after %s paid", async (funded) => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              invoices: [
                {
                  ...commercial.invoices[0],
                  status: "issued",
                  funded_amount: funded,
                  payment_status: funded === "107500.00" ? "paid" : "partially_paid",
                },
              ],
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByText("Invoice total").nextElementSibling).toHaveTextContent("₦107,500.00");
    expect(screen.getByText("Balance due").nextElementSibling).toHaveTextContent(
      funded === "107500.00" ? "₦0.00" : "₦57,500.00",
    );
  });
  it("keeps bank transfer available for a cancelled campaign with credit still due", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              accepts_payments: true,
              invoices: [
                { ...commercial.invoices[0], status: "issued", payment_status: "partially_paid" },
              ],
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : {
              data: {
                ...campaign,
                status: "cancelled",
                cancellation: { disposition: "credit_settlement_due" },
              },
            },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByRole("button", { name: "Check and record transfer" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Record funding approval" })).toBeNull();
  });

  it("shows nothing due on an invoice its campaign's cancellation closed", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              accepts_payments: false,
              invoices: [
                {
                  ...commercial.invoices[0],
                  status: "issued",
                  funded_amount: "0.00",
                  payment_status: "cancelled",
                },
              ],
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.queryByRole("button", { name: "Check and record transfer" })).toBeNull();
    expect(screen.getByText("Balance due").nextElementSibling).toHaveTextContent("₦0.00");
    expect(screen.getByText("Payment status").nextElementSibling).toHaveTextContent(
      "Cancelled – nothing to pay",
    );
  });
  beforeEach(() => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/commercial")) return { data: commercial };
      if (path === "/api/v1/admin/billing") return { data: [] };
      return { data: campaign };
    });
  });

  it("quotes per campaign with quantity, a 7.5 % VAT default and Nigeria-time dates", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? { data: { ...commercial, terms: null } }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByLabelText("Quantity (number of advert campaigns)")).toHaveValue(1);
    expect(screen.getByLabelText("Unit price before VAT")).toBeRequired();
    expect(screen.getByLabelText("VAT (%)")).toHaveValue("7.5");
    expect(screen.getByLabelText("Campaign start date")).toHaveValue("2026-10-01");
    expect(screen.getByLabelText("Campaign end date")).toHaveValue("2026-10-31");
    expect(screen.getByLabelText("Campaign start date")).toBeRequired();
    expect(screen.getByLabelText("Production amount before VAT (optional)")).not.toBeRequired();
  });

  it("pre-fills a new revision from the latest quotation before acceptance", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              terms: null,
              revisions: [
                {
                  quote_reference: "Q-OLD",
                  revision_number: 2,
                  currency: "NGN",
                  net_amount: "120000.00",
                  tax_amount: "9000.00",
                  gross_amount: "129000.00",
                  tax_rate: "0.075000",
                  payment_class: "standard_prepaid",
                  payment_terms: { notes: "Before printing" },
                  production_scope: {
                    vehicle_count: 3,
                    campaign_start_date: "2026-11-01",
                    campaign_end_date: "2026-11-30",
                  },
                  line_items: [
                    {
                      code: "M",
                      kind: "media",
                      description: "City campaign",
                      quantity: 2,
                      unit_amount: "50000.00",
                      amount: "100000.00",
                    },
                    { code: "P", kind: "production", description: "Fit wraps", amount: "20000.00" },
                  ],
                },
              ],
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByLabelText("VAT (%)")).toHaveValue("7.5");
    expect(screen.getByText("VAT").nextElementSibling).toHaveTextContent("7.5% · ₦9,000.00");
    expect(screen.getByLabelText("Quote reference")).toHaveValue("Q-OLD");
    expect(screen.getByLabelText("Services rendered")).toHaveValue("City campaign");
    expect(screen.getByLabelText("Quantity (number of advert campaigns)")).toHaveValue(2);
    expect(screen.getByLabelText("Unit price before VAT")).toHaveValue("50000.00");
    expect(screen.getByLabelText("Production amount before VAT (optional)")).toHaveValue(
      "20000.00",
    );
    expect(screen.getByLabelText("Campaign start date")).toHaveValue("2026-11-01");
    expect(screen.getByRole("button", { name: "Send quotation" })).toBeVisible();
  });

  it.each([false, true])(
    "offers invoice issuing only with configured authority: %s",
    async (available) => {
      get.mockImplementation(async (path: string) =>
        path.endsWith("/commercial")
          ? { data: { ...commercial, issuing_available: available } }
          : path === "/api/v1/admin/billing"
            ? { data: [] }
            : { data: campaign },
      );
      render(
        await AdminCampaignBillingPage({
          params: Promise.resolve({ campaignId: "campaign-1" }),
          searchParams: Promise.resolve({}),
        }),
      );
      expect(screen.queryByRole("button", { name: "Send quotation" })).toBeNull();
      expect(Boolean(screen.queryByRole("button", { name: "Issue invoice" }))).toBe(available);
      expect(Boolean(screen.queryByText(/bank details and the accountant's check/))).toBe(
        !available,
      );
      expect(screen.getByRole("link", { name: "View invoice" })).toHaveAttribute(
        "href",
        "/admin/campaigns/campaign-1?drawer=invoice&invoice=invoice-1#money",
      );
    },
  );
});

it("renders one section failure when its supporting money read fails", async () => {
  const normal = get.getMockImplementation()!;
  get.mockImplementation(async (path) =>
    path.endsWith("/billing") ? { data: undefined } : normal(path),
  );
  render(
    await AdminCampaignBillingPage({
      params: Promise.resolve({ campaignId: "campaign-1" }),
      searchParams: Promise.resolve({}),
      embedded: true,
    }),
  );
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent("This section couldn't be loaded.");
  expect(screen.queryByRole("heading", { name: "Quotation" })).toBeNull();
});
it.each([false, true])(
  "shows the current approval and an increase form after production: %s",
  async (started) => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              financial_authority: { max_driver_liability: "60000.00" },
              production_start: started ? { authority_basis: "prepaid_cash" } : null,
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByText(/Current maximum amount owed to drivers:/)).toHaveTextContent(
      "₦60,000.00",
    );
    expect(screen.getByLabelText("Maximum amount owed to drivers")).toBeRequired();
    expect(screen.getByLabelText("Supporting record and reason")).toBeRequired();
    expect(screen.getByRole("button", { name: "Record funding approval" })).toBeVisible();
    expect(Boolean(screen.queryByRole("button", { name: "Record production start" }))).toBe(
      !started,
    );
  },
);
it("shows the server's funding refusal in plain words", async () => {
  // REQ-316 F10: the URL carries a refusal code; the page shows its fixed copy.
  const plain = "The maximum amount owed to drivers cannot exceed the approved funding.";
  render(
    await AdminCampaignBillingPage({
      params: Promise.resolve({ campaignId: "campaign-1" }),
      searchParams: Promise.resolve({ error: "DRIVER_LIABILITY_EXCEEDS_AUTHORITY" }),
    }),
  );
  expect(screen.getByText(plain)).toBeVisible();
  expect(screen.getByText(plain)).toHaveClass("text-coral");
  expect(screen.getByRole("button", { name: "Record funding approval" })).toBeVisible();
});
it("never shows text taken from the URL", async () => {
  render(
    await AdminCampaignBillingPage({
      params: Promise.resolve({ campaignId: "campaign-1" }),
      searchParams: Promise.resolve({ error: "Call 0800 000 0000 to unlock payouts" }),
    }),
  );
  expect(screen.queryByText(/0800/)).toBeNull();
  expect(screen.getByText("That didn't work. Refresh the page and try again.")).toHaveClass(
    "text-coral",
  );
});
describe("manual transfer result on the Money tab (mocked end-to-end)", () => {
  // The real transfer action runs against a mocked API; its actual redirect feeds the real page.
  async function transferThenRender(response: unknown, observed: string, expected: string) {
    vi.clearAllMocks();
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? { data: commercial }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    post.mockResolvedValueOnce(response);
    const { recordManualTransferAction } =
      await vi.importActual<typeof import("./actions")>("./actions");
    const form = new FormData();
    form.set("observed_amount", observed);
    form.set("expected_amount", expected);
    await expect(
      recordManualTransferAction("campaign-1", "org-1", "terms-1", form),
    ).rejects.toThrow("redirect:");
    expect((post.mock.calls[0]![1] as { body: unknown }).body).toMatchObject({
      observed_amount: observed,
      expected_amount: expected,
    });
    expect(revalidatePath).toHaveBeenCalledWith("/admin/campaigns/campaign-1");
    const url = new URL(String(redirect.mock.calls[0]![0]), "https://cardvert.test");
    expect(url.pathname).toBe("/admin/campaigns/campaign-1");
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({ saved: url.searchParams.get("saved") ?? undefined }),
      }),
    );
    return screen.getByRole("status");
  }

  it("shows a matched transfer as applied, in the success colour", async () => {
    const status = await transferThenRender({ data: { matched: true } }, "107500.00", "107500.00");
    expect(status).toHaveTextContent("Transfer recorded and applied to the invoice.");
    expect(status).toHaveClass("text-green");
    expect(status).not.toHaveClass("text-terrax-gold-ink");
  });

  it("warns, in a distinct colour, that a mismatched transfer was not applied", async () => {
    const status = await transferThenRender({ data: { matched: false } }, "100.00", "107500.00");
    expect(status).toHaveTextContent(
      "Transfer recorded but not applied: the amount doesn't match the expected amount.",
    );
    expect(status).toHaveClass("text-terrax-gold-ink");
    expect(status).not.toHaveClass("text-green");
  });

  it("never shows an unreadable result as applied", async () => {
    const status = await transferThenRender({ data: undefined }, "107500.00", "107500.00");
    expect(status).toHaveTextContent("We couldn't confirm the transfer result.");
    expect(status).toHaveClass("text-terrax-gold-ink");
    expect(status).not.toHaveClass("text-green");
  });
});

it.each(["toString", "Transfer applied, call 0800"])(
  "shows no confirmation for an unknown saved code (%s)",
  async (saved) => {
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({ saved }),
      }),
    );
    expect(screen.queryByText(/0800/)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  },
);
it("asks only for the amount before VAT on an issued invoice's correction", async () => {
  get.mockImplementation(async (path: string) =>
    path.endsWith("/commercial")
      ? {
          data: {
            ...commercial,
            invoices: [{ ...commercial.invoices[0]!, status: "issued", invoice_number: "TXM-1" }],
          },
        }
      : path === "/api/v1/admin/billing"
        ? { data: [] }
        : { data: campaign },
  );
  const { container } = render(
    await AdminCampaignBillingPage({
      params: Promise.resolve({ campaignId: "campaign-1" }),
      searchParams: Promise.resolve({}),
    }),
  );
  expect(screen.getByLabelText("Amount before VAT")).toBeRequired();
  expect(container.querySelector('input[name="tax_amount"]')).toBeNull();
  expect(
    screen.getByText("VAT is added at the invoice's rate when you record the correction."),
  ).toBeVisible();
});
it.each([
  ["draft", false],
  ["void", false],
  ["none", false],
  ["issued", true],
] as const)(
  "offers manual transfer recording only for an issued invoice: %s",
  async (state, shown) => {
    const invoices =
      state === "none"
        ? []
        : [{ ...commercial.invoices[0]!, status: state, invoice_number: "TXM-1" }];
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? { data: { ...commercial, invoices } }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.queryByText(/Unknown status/)).toBeNull();
    if (state === "void") expect(screen.getByText("Voided")).toBeVisible();
    if (!shown && state !== "none") {
      expect(screen.getByText("Balance due").nextElementSibling).toHaveTextContent("—");
    }
    expect(Boolean(screen.queryByRole("button", { name: "Check and record transfer" }))).toBe(
      shown,
    );
    expect(Boolean(screen.queryByRole("heading", { name: "Manual bank transfer" }))).toBe(shown);
  },
);

describe("custom quotation request", () => {
  it("shows staff the advertiser's note from the request", async () => {
    get.mockImplementation(async (path: string) =>
      path.endsWith("/commercial")
        ? {
            data: {
              ...commercial,
              terms: null,
              invoices: [],
              quote_request: {
                id: "quote-1",
                request_details: { notes: "Please quote for weekend lunch deliveries." },
              },
            },
          }
        : path === "/api/v1/admin/billing"
          ? { data: [] }
          : { data: campaign },
    );
    render(
      await AdminCampaignBillingPage({
        params: Promise.resolve({ campaignId: "campaign-1" }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByText("Advertiser's note")).toBeVisible();
    expect(screen.getByText("Please quote for weekend lunch deliveries.")).toBeVisible();
  });
});
