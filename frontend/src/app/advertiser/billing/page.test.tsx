import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("./actions", () => ({ startInvoicePayment: vi.fn() }));

import AdvertiserBillingPage from "./page";

const TERMS_ID = "00000000-0000-0000-0000-000000000031";

const receipt = (id: string, reference: string) => ({
  id,
  external_transaction_id: reference,
  payer_name: "Demo Advertiser",
  observed_at: "2026-09-01T10:00:00Z",
  amount: "250000.00",
  currency: "NGN",
});

const allocation = (id: string, termsId: string, amount: string) => ({
  id,
  receipt_id: "r",
  commercial_terms_id: termsId,
  amount,
  currency: "NGN",
  allocated_at: "2026-09-01T10:00:00Z",
});

const invoice = (overrides: Record<string, unknown>) => ({
  id: "00000000-0000-0000-0000-000000000041",
  campaign_id: "campaign-1",
  commercial_terms_id: TERMS_ID,
  organization_id: "org-1",
  invoice_number: "INV-2026-0007",
  status: "issued",
  payment_status: "partially_paid",
  currency: "NGN",
  net_amount: "232558.14",
  tax_rate: "0.0750",
  tax_amount: "17441.86",
  gross_amount: "250000.00",
  effective_obligation_amount: "250000.00",
  funded_amount: "100000.00",
  line_items: [],
  customer_snapshot: {},
  issuer_profile_id: null,
  issuer_snapshot: null,
  issued_at: "2026-09-01T09:00:00Z",
  created_at: "2026-09-01T09:00:00Z",
  corrections: [],
  ...overrides,
});

function mockBilling(receipts: unknown[], invoices: unknown[] = []) {
  get.mockImplementation(async (path?: string) => {
    if (path === "/api/v1/advertiser/billing") return { data: receipts };
    if (path === "/api/v1/advertiser/campaigns") {
      return {
        data: {
          items: invoices.length ? [{ id: "campaign-1", name: "Lunch Routes" }] : [],
          total: invoices.length ? 1 : 0,
        },
      };
    }
    return { data: { terms: { id: TERMS_ID }, invoices, settlements: [] } };
  });
}

describe("AdvertiserBillingPage", () => {
  beforeEach(() => get.mockReset());

  it("orders the page as what is owed, what was paid, then invoice history", async () => {
    mockBilling(
      [
        {
          receipt: receipt("r1", "TRF-001"),
          current_status: "confirmed",
          allocations: [],
          events: [],
        },
      ],
      [invoice({})],
    );

    render(await AdvertiserBillingPage({}));

    expect(screen.getByRole("heading", { level: 1, name: "Billing" })).toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent),
    ).toEqual(["To pay", "Payments", "Invoice history"]);
    const toPay = screen.getByRole("region", { name: "To pay" });
    expect(within(toPay).getByText("Invoice INV-2026-0007")).toBeInTheDocument();
    expect(within(toPay).getByText("Part paid")).toBeInTheDocument();
    expect(within(toPay).getByText("Lunch Routes")).toBeInTheDocument();
    expect(within(toPay).getByText("₦150,000 left to pay")).toBeInTheDocument();
    expect(within(toPay).getByText("of ₦250,000")).toBeInTheDocument();
    expect(within(toPay).getByText("₦100,000 paid so far")).toBeInTheDocument();
    expect(within(toPay).getByRole("button", { name: "Pay invoice online" })).toBeInTheDocument();
    expect(within(toPay).getAllByText(/Card or bank transfer through Paystack/)).toHaveLength(1);
    const payForm = within(toPay)
      .getByRole("button", { name: "Pay invoice online" })
      .closest("form")!;
    expect(
      within(payForm).queryByText(/Card or bank transfer through Paystack/),
    ).not.toBeInTheDocument();
    const invoiceHistory = screen.getByRole("region", { name: "Invoice history" });
    expect(within(invoiceHistory).getByRole("link", { name: "Lunch Routes" })).toBeInTheDocument();
    expect(within(invoiceHistory).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/Persisted invoices|lineage/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Manual bank transfer remains available/)).not.toBeInTheDocument();
  });

  it("says what each payment was put towards in plain words", async () => {
    mockBilling(
      [
        {
          receipt: receipt("r1", "TRF-001"),
          current_status: null,
          allocations: [],
          events: [],
        },
        {
          receipt: receipt("r2", "TRF-002"),
          current_status: "reconciled",
          allocations: [],
          events: [],
        },
        {
          receipt: receipt("r3", "TRF-003"),
          current_status: "confirmed",
          allocations: [
            allocation("a1", TERMS_ID, "150000.00"),
            allocation("a2", "00000000-0000-0000-0000-000000000099", "100000.00"),
          ],
          events: [],
        },
        {
          receipt: receipt("r4", "TRF-004"),
          current_status: "reversed",
          allocations: [allocation("a3", TERMS_ID, "250000.00")],
          events: [],
        },
      ],
      [invoice({ payment_status: "paid", funded_amount: "250000.00" })],
    );

    render(await AdvertiserBillingPage({}));

    const payments = screen.getByRole("region", { name: "Payments" });
    expect(within(payments).getByText("Recorded – being checked")).toBeInTheDocument();
    expect(
      within(payments).getByText("Amount matched – awaiting confirmation"),
    ).toBeInTheDocument();
    expect(within(payments).getByText("Confirmed")).toBeInTheDocument();
    expect(within(payments).getByText("Reversed")).toBeInTheDocument();
    expect(within(payments).getByText("Paid towards: Lunch Routes · ₦150,000")).toBeInTheDocument();
    expect(
      within(payments).getByText("Paid towards: a campaign's accepted quotation · ₦100,000"),
    ).toBeInTheDocument();
    expect(
      within(payments).getAllByText(
        "Not yet matched to a campaign – production cannot start from this payment.",
      ),
    ).toHaveLength(2);
    expect(
      within(payments).getByText("Reversed – this payment no longer counts towards any campaign."),
    ).toBeInTheDocument();
    expect(within(payments).getAllByText("₦250,000")).toHaveLength(4);
    expect(screen.getByText("Nothing to pay right now.")).toBeInTheDocument();
    expect(screen.queryByText(/allocation|canonical|immutable|provider/i)).not.toBeInTheDocument();
  });

  it("shows plain empty states when nothing has been billed", async () => {
    mockBilling([]);

    render(await AdvertiserBillingPage({}));

    expect(screen.getByText("Nothing to pay right now.")).toBeInTheDocument();
    expect(screen.getByText("No payments have been recorded yet.")).toBeInTheDocument();
    expect(screen.getByText("No invoices yet.")).toBeInTheDocument();
  });

  it.each([
    ["confirmed", "Payment confirmed", "The verified payment is being applied to the invoice."],
    [
      "failed",
      "Paystack did not complete the payment",
      "No payment is treated as complete until Paystack confirms it.",
    ],
    [
      "pending",
      "Payment confirmation is still pending",
      "No payment is treated as complete until Paystack confirms it.",
    ],
    ["error", "Online payment could not be opened", "Please try again from the invoice."],
  ])("explains a %s Paystack return in plain language", async (payment, heading, message) => {
    mockBilling([]);

    render(
      await AdvertiserBillingPage({
        searchParams: Promise.resolve({
          payment,
          ...(payment === "error" ? { message } : {}),
        }),
      }),
    );

    expect(screen.getByRole("status")).toHaveTextContent(heading);
    expect(screen.getByRole("status")).toHaveTextContent(message);
  });
});
