import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({ user: { id: "admin-1" } }),
}));
vi.mock("next/navigation", () => ({ notFound: vi.fn() }));
vi.mock("./actions", () => ({
  createInvoiceAction: vi.fn(),
  recordBudgetBlockedStateAction: vi.fn(),
  recordFinancialAuthorityAction: vi.fn(),
  recordInvoiceCorrectionAction: vi.fn(),
  recordManualTransferAction: vi.fn(),
  recordProductionStartAction: vi.fn(),
  recordRefundAction: vi.fn(),
  recordRevisionAction: vi.fn(),
  reverseReceiptAction: vi.fn(),
}));

import AdminCampaignBillingPage from "./page";

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
    expect(screen.getByRole("link", { name: "View invoice" })).toHaveAttribute(
      "href",
      "/admin/billing/campaign-1/invoices/invoice-1",
    );
  });
});
