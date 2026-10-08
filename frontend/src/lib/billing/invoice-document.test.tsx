import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import {
  formatCampaignDuration,
  formatInvoiceDate,
  formatVatRate,
  InvoiceDocument,
  watCalendarDate,
} from "./invoice-document";

type Invoice = components["schemas"]["InvoiceRead"];
type Terms = components["schemas"]["CommercialTermsRead"];

const issued: Invoice = {
  id: "invoice-1",
  campaign_id: "campaign-1",
  commercial_terms_id: "terms-1",
  organization_id: "org-1",
  issuer_profile_id: "issuer-1",
  invoice_number: "TEST-CV-2026-000001",
  status: "issued",
  payment_status: "partially_paid",
  currency: "NGN",
  net_amount: "370001.00",
  tax_rate: "0.075000",
  tax_amount: "27750.08",
  gross_amount: "397751.08",
  effective_obligation_amount: "386998.58",
  funded_amount: "50000.00",
  line_items: [
    {
      code: "MEDIA",
      description: "Mobile billboard campaign",
      kind: "media",
      amount: "300000.00",
      quantity: 3,
      unit_amount: "100000.00",
      metadata: {},
    },
    { code: "DESIGN", description: "Graphic design", kind: "other", amount: "70001.00" },
  ],
  customer_snapshot: {
    name: "Acme Foods Ltd",
    billing_contact_name: "Ada Obi",
    billing_email: "billing@acme.example",
    billing_contact_phone: "0800 000 0000",
    address: { line_1: "1 Test Road", city: "Abuja", country_code: "NG" },
  },
  issuer_snapshot: {
    legal_name: "Terrax Media Company Ltd",
    registered_address: "Test fixture address, Abuja",
    contact_phone: "TEST-PHONE",
    contact_email: "invoices@example.com",
    company_registration_number: "TEST-RC",
    tax_identification_number: "TEST-TIN",
    bank_name: "Test Bank",
    bank_account_name: "Terrax Media Company Ltd",
    bank_account_number: "TEST-ACCOUNT",
    invoice_wording: "Prices include 7.5% VAT.",
    external_input_reference: "INTERNAL-GATE-REFERENCE",
    synthetic_test_authority: true,
  },
  corrections: [
    {
      id: "correction-1",
      invoice_id: "invoice-1",
      sequence_number: 1,
      correction_number: "TEST-CV-2026-000001-C01",
      correction_reference: "internal-correction-reference",
      correction_type: "credit_note",
      currency: "NGN",
      net_amount: "10002.33",
      tax_amount: "750.17",
      gross_amount: "10752.50",
      reason: "One campaign day cancelled",
      created_at: "2026-10-02T09:00:00Z",
    },
  ],
  // 23:30 UTC on 31 October is already 1 November in Nigeria.
  issued_at: "2026-10-31T23:30:00Z",
  created_at: "2026-10-01T09:00:00Z",
};

const terms = {
  payment_class: "standard_prepaid",
  production_scope: {
    vehicle_count: 3,
    campaign_start_date: "2026-10-01",
    campaign_end_date: "2026-10-31",
  },
} as unknown as Terms;

function fact(label: string) {
  const term = screen.getAllByText(label).find((element) => element.tagName === "DT");
  return term?.nextElementSibling?.textContent;
}

describe("InvoiceDocument", () => {
  it("lays out an issued invoice with every field the client asked for", () => {
    render(<InvoiceDocument invoice={issued} terms={terms} campaignName="October launch" />);

    expect(screen.getByRole("heading", { name: "Test invoice" })).toBeVisible();
    expect(fact("Invoice number (serial no.)")).toBe("TEST-CV-2026-000001");
    expect(fact("Date issued (Nigeria time, WAT)")).toBe("1 November 2026");
    expect(fact("RC number")).toBe("TEST-RC");
    expect(fact("TIN")).toBe("TEST-TIN");
    expect(fact("Client name")).toBe("Ada Obi");
    expect(screen.getByText("1 Test Road, Abuja, NG")).toBeVisible();
    expect(fact("Campaign")).toBe("October launch");
    expect(fact("Campaign duration")).toBe("1 October 2026 – 31 October 2026 (31 days)");
    expect(fact("Payment arrangement")).toBe("Paid in full before production");

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("1Mobile billboard campaign3₦100,000.00₦300,000.00");
    // A line entered before quantities existed reads as one unit.
    expect(rows[2]).toHaveTextContent("2Graphic design1₦70,001.00₦70,001.00");

    expect(fact("Subtotal (before VAT)")).toBe("₦370,001.00");
    expect(fact("Included VAT")).toBe("VAT 7.5% · ₦27,750.08");
    expect(fact("Invoice total (VAT inclusive)")).toBe("₦397,751.08");
    expect(screen.getByText(/One campaign day cancelled/)).toHaveTextContent(
      "Credit note: reduces the invoice by ₦10,752.50 (₦10,002.33 + VAT ₦750.17)",
    );
    expect(fact("Amount after corrections (VAT inclusive)")).toBe("₦386,998.58");
    expect(fact("Paid so far")).toBe("₦50,000.00");
    expect(fact("Payment status")).toBe("Part paid");
    expect(fact("Account number")).toBe("TEST-ACCOUNT");
    expect(screen.getByText("Prices include 7.5% VAT.")).toBeVisible();
    expect(screen.getByText("For the client")).toBeVisible();
    expect(screen.getByText("For Terrax Media Company Ltd")).toBeVisible();
    expect(screen.getByText("Chief Executive Officer")).toBeVisible();
    expect(screen.getAllByText("Signature:")).toHaveLength(2);
    // Internal references never reach the page (D38c).
    expect(document.body).not.toHaveTextContent("INTERNAL-GATE-REFERENCE");
    expect(document.body).not.toHaveTextContent("internal-correction-reference");
  });

  it("marks a draft, leaves unrecorded facts blank and shows no payments block", () => {
    const draft: Invoice = {
      ...issued,
      status: "draft",
      invoice_number: null,
      issued_at: null,
      issuer_profile_id: null,
      issuer_snapshot: null,
      corrections: [],
      customer_snapshot: { name: "Acme Foods Ltd" },
    };
    render(<InvoiceDocument invoice={draft} terms={null} campaignName="October launch" />);

    expect(screen.getByRole("heading", { name: "Draft invoice" })).toBeVisible();
    expect(screen.getByText(/Not for payment/)).toBeVisible();
    expect(screen.getByText("Terrax Media Company Ltd")).toBeVisible();
    expect(fact("Invoice number (serial no.)")).toBe("Not yet recorded");
    expect(fact("Campaign duration")).toBe("Not yet recorded");
    expect(fact("Payment arrangement")).toBe("Not yet recorded");
    expect(fact("Bank")).toBe("Not yet recorded");
    expect(fact("Account number")).toBe("Not yet recorded");
    expect(screen.queryByText("Corrections and payments")).not.toBeInTheDocument();
    expect(screen.getByText("For Terrax Media")).toBeVisible();
  });

  it("names a real issued or void invoice plainly", () => {
    const real: Invoice = {
      ...issued,
      corrections: issued.corrections!.map((correction) => ({
        ...correction,
        correction_type: "debit_note",
      })),
      payment_status: "paid",
      issuer_snapshot: { ...issued.issuer_snapshot, synthetic_test_authority: false },
    };
    const { unmount } = render(
      <InvoiceDocument invoice={real} terms={terms} campaignName="October launch" />,
    );
    expect(screen.getByRole("heading", { name: "Invoice" })).toBeVisible();
    expect(screen.getByText(/Debit note: adds ₦10,752.50 to the invoice/)).toBeVisible();
    expect(fact("Payment status")).toBe("Paid");
    unmount();
    // Void wins over the test label, so a voided test invoice never reads as live.
    render(
      <InvoiceDocument invoice={{ ...issued, status: "void" }} terms={terms} campaignName="x" />,
    );
    expect(screen.getByRole("heading", { name: "Void invoice" })).toBeVisible();
  });
});

describe("invoice formatting", () => {
  it("formats rates, dates and durations without guessing", () => {
    expect(formatVatRate("0.075000")).toBe("7.5%");
    expect(formatVatRate("0")).toBe("0%");
    expect(formatVatRate("not-a-rate")).toBe("—");
    expect(formatInvoiceDate(null)).toBe("Not yet recorded");
    expect(formatInvoiceDate("not-a-date")).toBe("Not yet recorded");
    expect(formatCampaignDuration({ campaign_start_date: "2026-10-01" })).toBe("Not yet recorded");
    expect(
      formatCampaignDuration({ campaign_start_date: "2026-10-01", campaign_end_date: "bad" }),
    ).toBe("Not yet recorded");
    expect(
      formatCampaignDuration({
        campaign_start_date: "2026-10-01",
        campaign_end_date: "2026-10-01",
      }),
    ).toBe("1 October 2026 – 1 October 2026 (1 day)");
    expect(formatCampaignDuration(undefined)).toBe("Not yet recorded");
  });

  it("reads a campaign instant as its Nigeria calendar day", () => {
    expect(watCalendarDate("2026-09-30T23:00:00Z")).toBe("2026-10-01");
    expect(watCalendarDate("2026-09-30T22:59:59Z")).toBe("2026-09-30");
    expect(watCalendarDate(null)).toBe("");
    expect(watCalendarDate("bad")).toBe("");
  });
});
