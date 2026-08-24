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
  disposition: "refunded",
  amount: "20.00",
  currency: "NGN",
  settlement_provider: "manual_bank",
  external_reference: "REF-100",
  reason: "Reversal settlement",
  funding_authorized_at: "2026-08-24T10:00:00Z",
  eligibility_ends_at: "2026-08-25T10:00:00Z",
  recorded_at: "2026-08-24T12:00:00Z",
};

describe("CommercialHistory", () => {
  it("renders API-derived obligation, correction and settlement lineage", () => {
    render(<CommercialHistory invoices={[invoice]} settlements={[settlement]} />);

    expect(screen.getByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("partially paid")).toBeInTheDocument();
    expect(screen.getByText(/CN-2026-0001/)).toBeInTheDocument();
    expect(screen.getByText(/Reduced vehicle count/)).toBeInTheDocument();
    expect(screen.getByText("refunded")).toBeInTheDocument();
    expect(screen.getByText(/REF-100/)).toBeInTheDocument();
  });
});
