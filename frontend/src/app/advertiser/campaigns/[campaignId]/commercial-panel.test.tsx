import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { components } from "@/lib/api/schema";

vi.mock("./commercial-actions", () => ({
  acceptExpeditedWaiverAction: vi.fn(),
  acceptQuoteAction: vi.fn(),
  requestQuoteAction: vi.fn(),
}));

import { CommercialPanel } from "./commercial-panel";

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

describe("CommercialPanel copy", () => {
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
          revisions: [
            {
              id: "rev1",
              quote_reference: "Q-100",
              revision_number: 2,
              net_amount: "100000.00",
              tax_amount: "7500.00",
              gross_amount: "107500.00",
              currency: "NGN",
            } as Commercial["revisions"][number],
          ],
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Accept final terms" })).toBeInTheDocument();
    expect(screen.getByText(/₦100,000 net \+ ₦7,500 VAT · ₦107,500 total/)).toBeInTheDocument();
  });

  it("labels the accepted funding basis plainly", () => {
    render(
      <CommercialPanel
        campaignId={CAMPAIGN_ID}
        commercial={commercial({
          terms: { payment_class: "approved_credit" } as Commercial["terms"],
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
