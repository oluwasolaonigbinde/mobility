import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({ user: { id: "admin-1" } }),
}));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  notFound: vi.fn(),
}));
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
}));

import AdminCampaignBillingPage from "./content";

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
  financial_authority: null,
  production_start: null,
  waiver: null,
};

describe("admin campaign billing page", () => {
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
    expect(screen.getByLabelText("VAT rate (decimal, 0.075 = 7.5 %)")).toHaveValue("0.075");
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
                  tax_rate: "0.075",
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
    expect(screen.getByLabelText("Quote reference")).toHaveValue("Q-OLD");
    expect(screen.getByLabelText("Services rendered")).toHaveValue("City campaign");
    expect(screen.getByLabelText("Quantity (number of advert campaigns)")).toHaveValue(2);
    expect(screen.getByLabelText("Unit price before VAT")).toHaveValue("50000.00");
    expect(screen.getByLabelText("Production amount before VAT (optional)")).toHaveValue(
      "20000.00",
    );
    expect(screen.getByLabelText("Campaign start date")).toHaveValue("2026-11-01");
    expect(screen.getByRole("button", { name: "Save quotation version" })).toBeVisible();
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
      expect(screen.queryByRole("button", { name: "Save quotation version" })).toBeNull();
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
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
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
  render(
    await AdminCampaignBillingPage({
      params: Promise.resolve({ campaignId: "campaign-1" }),
      searchParams: Promise.resolve({ error: "Not enough cleared funding for this approval." }),
    }),
  );
  expect(screen.getByText("Not enough cleared funding for this approval.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Record funding approval" })).toBeVisible();
});
