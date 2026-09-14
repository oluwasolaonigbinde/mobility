import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { components } from "@/lib/api/schema";

vi.mock("./commercial-actions", () => ({
  acceptExpeditedWaiverAction: vi.fn(),
  acceptQuoteAction: vi.fn(),
  requestQuoteAction: vi.fn(),
}));

import { CommercialPanel } from "./commercial-panel";
import { requestQuoteAction } from "./commercial-actions";

type Commercial = components["schemas"]["CampaignCommercialRead"];

const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000001";

function commercial(overrides: Partial<Commercial> = {}): Commercial {
  return {
    budget_evaluations: [],
    expedited_waiver_copy: {
      accepted_wording: "I waive the wait.",
      accepted_wording_hash: "h",
      wording_version: "v1",
    },
    financial_authority: null,
    invoices: [],
    production_start: null,
    quote_request: null,
    revisions: [],
    settlements: [],
    terms: null,
    waiver: null,
    ...overrides,
  } as Commercial;
}

function revision(overrides: Partial<Commercial["revisions"][number]> = {}) {
  return {
    id: "00000000-0000-4000-8000-000000000002",
    quote_request_id: "00000000-0000-4000-8000-000000000003",
    campaign_id: CAMPAIGN_ID,
    organization_id: "00000000-0000-4000-8000-000000000004",
    quote_reference: "Q-100",
    revision_number: 2,
    line_items: [
      {
        code: "PRINT",
        description: "Vehicle wrap production",
        kind: "production",
        amount: "100000.00",
      },
    ],
    production_scope: { vehicle_count: 4, available_from: "2026-10-01" },
    production_cost_amount: "100000.00",
    payment_class: "standard_prepaid",
    payment_terms: { due: "before production", available_date: "2026-10-01" },
    net_amount: "100000.00",
    tax_rate: "0.0750",
    tax_amount: "7500.00",
    gross_amount: "107500.00",
    currency: "NGN",
    created_at: "2026-09-14T12:00:00Z",
    ...overrides,
  } as Commercial["revisions"][number];
}

describe("CommercialPanel copy", () => {
  it("keeps visible request success through the authoritative commercial refresh", async () => {
    const user = userEvent.setup();
    vi.mocked(requestQuoteAction).mockResolvedValueOnce({
      done: "Quotation requested. Cardvert will post it here for review.",
    });
    const view = render(<CommercialPanel campaignId={CAMPAIGN_ID} commercial={commercial()} />);
    await user.type(screen.getByLabelText("Quotation notes"), "Four vehicle placement");
    await user.click(screen.getByRole("button", { name: "Request custom quotation" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Quotation requested");

    view.rerender(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({ quote_request: { id: "q1" } as Commercial["quote_request"] })}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Quotation requested");
    const submitted = vi.mocked(requestQuoteAction).mock.calls[0]?.[1];
    expect(submitted).toBeInstanceOf(FormData);
    expect(submitted?.get("campaign_id")).toBe(CAMPAIGN_ID);
    expect(submitted?.get("notes")).toBe("Four vehicle placement");
  });

  it("tells the advertiser what happens after a quotation request", () => {
    render(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({ quote_request: { id: "q1" } as Commercial["quote_request"] })}
      />,
    );

    expect(screen.getByText("Your quotation, payment and production status")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your request has been received. Our team will prepare a quotation for you to review here.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/immutable|structured revision/i)).not.toBeInTheDocument();
  });

  it("keeps acceptance final and the quoted amounts unchanged", () => {
    render(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({
          quote_request: { id: "q1" } as Commercial["quote_request"],
          revisions: [revision()],
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Accept these exact terms" })).toBeInTheDocument();
    expect(screen.getByText("Vehicle wrap production")).toBeInTheDocument();
    expect(screen.getAllByText("NGN 100000.00")).toHaveLength(3);
    expect(screen.getByText(/0.0750 · NGN 7500.00/)).toBeInTheDocument();
    expect(screen.getByText("NGN 107500.00")).toBeInTheDocument();
    expect(screen.getByText(/before production/)).toBeInTheDocument();
    expect(screen.getAllByText(/2026-10-01/)).toHaveLength(2);
    expect(
      screen.getByText(/I reviewed the scope, every line item, production cost, tax, exact total/),
    ).toBeInTheDocument();
  });

  it("keeps the accepted revision visible as an immutable receipt", () => {
    const accepted = {
      ...revision(),
      quotation_revision_id: "00000000-0000-4000-8000-000000000002",
      quotation_revision_number: 2,
      standard_production_wait_hours: 24,
      acceptance_method: "in_platform",
      accepted_at: "2026-09-14T12:30:00Z",
    } as Commercial["terms"];
    render(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({ revisions: [revision({ revision_number: 3 })], terms: accepted })}
      />,
    );

    expect(screen.getByText("Accepted quotation receipt")).toBeInTheDocument();
    expect(screen.getByText(/Q-100 · revision 2/)).toBeInTheDocument();
    expect(screen.getByText("Accepted and fixed")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Accept these exact terms/ }),
    ).not.toBeInTheDocument();
  });

  it("labels the accepted funding basis plainly", () => {
    const accepted = {
      ...revision(),
      quotation_revision_id: "00000000-0000-4000-8000-000000000002",
      quotation_revision_number: 2,
      standard_production_wait_hours: 24,
      acceptance_method: "in_platform",
      accepted_at: "2026-09-14T12:30:00Z",
    } as Commercial["terms"];
    render(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({
          terms: { ...accepted, payment_class: "approved_credit" } as Commercial["terms"],
          financial_authority: {
            authority_type: "approved_credit",
            authorized_amount: "50000.00",
            currency: "NGN",
          } as Commercial["financial_authority"],
        })}
      />,
    );

    expect(screen.getByText("Payment basis")).toBeInTheDocument();
    expect(screen.getByText("approved credit · ₦50,000")).toBeInTheDocument();
    expect(screen.queryByText("Funding authority")).not.toBeInTheDocument();
  });
});
