import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { CommercialHistory } from "./commercial-history";

type Invoice = components["schemas"]["InvoiceRead"];
type Settlement = components["schemas"]["SettlementRead"];

const invoice: Invoice = {
  id: "00000000-0000-0000-0000-000000000001",
  campaign_id: "00000000-0000-0000-0000-000000000002",
  commercial_terms_id: "00000000-0000-0000-0000-000000000003",
  organization_id: "00000000-0000-0000-0000-000000000004",
  invoice_number: "INV-2026-0001",
  status: "issued",
  payment_status: "partially_paid",
  currency: "NGN",
  net_amount: "100.00",
  tax_rate: "0.0750",
  tax_amount: "7.50",
  gross_amount: "107.50",
  effective_obligation_amount: "96.75",
  funded_amount: "50.00",
  line_items: [],
  customer_snapshot: {},
  issuer_profile_id: "00000000-0000-0000-0000-000000000005",
  issuer_snapshot: {},
  issued_at: "2026-08-24T10:00:00Z",
  created_at: "2026-08-24T09:00:00Z",
  corrections: [
    {
      id: "00000000-0000-0000-0000-000000000006",
      invoice_id: "00000000-0000-0000-0000-000000000001",
      correction_number: "CN-2026-0001",
      correction_reference: "test-correction-reference",
      sequence_number: 1,
      correction_type: "credit_note",
      currency: "NGN",
      net_amount: "10.00",
      tax_amount: "0.75",
      gross_amount: "10.75",
      reason: "Reduced vehicle count",
      created_at: "2026-08-24T11:00:00Z",
    },
  ],
};

const settlement: Settlement = {
  id: "00000000-0000-0000-0000-000000000007",
  campaign_id: "00000000-0000-0000-0000-000000000002",
  commercial_terms_id: "00000000-0000-0000-0000-000000000003",
  receipt_id: "00000000-0000-0000-0000-000000000008",
  cancellation_id: null,
  disposition: "refunded",
  amount: "20.00",
  currency: "NGN",
  settlement_provider: "manual_bank",
  external_reference: "REF-100",
  reason: "Reversal settlement",
  funding_authorized_at: "2026-08-24T10:00:00Z",
  eligibility_ends_at: "2026-08-25T10:00:00Z",
  eligibility_evaluated_at: null,
  recorded_at: "2026-08-24T12:00:00Z",
};

describe("CommercialHistory", () => {
  it("shows invoices, corrections and refunds as plain lines", () => {
    const { container } = render(
      <CommercialHistory
        invoices={[invoice]}
        settlements={[{ ...settlement, disposition: "refund_recorded" }]}
        showPayment
      />,
    );

    expect(screen.getByRole("heading", { name: "Invoice history" })).toBeInTheDocument();
    expect(screen.getByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("Part paid")).toBeInTheDocument();
    expect(
      screen.getByText("₦96.75 total (was ₦107.50 before corrections) · ₦50.00 paid"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /^Credit note CN-2026-0001: ₦10\.75 including VAT · Reduced vehicle count · /,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Refund: ₦20\.00 · Reversal settlement · .* · reference REF-100$/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pay invoice online" })).toBeInTheDocument();
    expect(
      screen.getByText(/The invoice shows as paid once Paystack confirms the payment/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View invoice" })).toHaveAttribute(
      "href",
      "/advertiser/campaigns/00000000-0000-0000-0000-000000000002/invoices/00000000-0000-0000-0000-000000000001",
    );
    expect(container.textContent).not.toMatch(/Persisted|lineage|_/);
  });

  it("names the campaign and leaves payment to the To pay list when asked", () => {
    render(
      <CommercialHistory
        campaign={{ id: "campaign-9", name: "Lunch Routes" }}
        invoices={[invoice]}
        settlements={[]}
        showPayment={false}
      />,
    );

    expect(screen.getByRole("link", { name: "Lunch Routes" })).toHaveAttribute(
      "href",
      "/advertiser/campaigns/campaign-9",
    );
    expect(screen.queryByRole("button", { name: "Pay invoice online" })).not.toBeInTheDocument();
  });

  it.each([
    ["fully funded", { funded_amount: "96.75" }],
    ["over funded", { funded_amount: "100.00" }],
    ["unreadable", { effective_obligation_amount: "bad" }],
  ])("offers no payment for an issued invoice that is %s", (_name, change) => {
    render(
      <CommercialHistory invoices={[{ ...invoice, ...change }]} settlements={[]} showPayment />,
    );
    expect(screen.queryByRole("button", { name: "Pay invoice online" })).not.toBeInTheDocument();
  });
});
