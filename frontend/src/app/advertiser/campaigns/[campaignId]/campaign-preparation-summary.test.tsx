import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { components } from "@/lib/api/schema";
import { CampaignPreparationSummary } from "./campaign-preparation-summary";

type Campaign = components["schemas"]["CampaignRead"];
type Commercial = components["schemas"]["CampaignCommercialRead"];
type Creative = components["schemas"]["CreativeRead"];

const campaign = { id: "c1", status: "draft" } as Campaign;
const commercial = {
  quote_request: null,
  revisions: [],
  terms: null,
  financial_authority: null,
} as unknown as Commercial;

describe("CampaignPreparationSummary", () => {
  it("shows one next action from recorded facts without inventing launch authority", () => {
    render(
      <CampaignPreparationSummary campaign={campaign} commercial={commercial} creatives={[]} />,
    );
    expect(screen.getByText(/Next action: Request the custom quotation/)).toBeInTheDocument();
    expect(
      screen.getByText(/does not authorize production, assignment, installation or launch/),
    ).toBeInTheDocument();
  });

  it("prioritizes rejected artwork after accepted terms", () => {
    render(
      <CampaignPreparationSummary
        campaign={campaign}
        commercial={
          {
            ...commercial,
            quote_request: { id: "q1" },
            revisions: [{ id: "r1" }],
            terms: { id: "t1" },
          } as Commercial
        }
        creatives={[{ status: "rejected" } as Creative]}
      />,
    );
    expect(screen.getByText(/Next action: Replace or update rejected artwork/)).toBeInTheDocument();
    expect(screen.getByText("Changes required")).toBeInTheDocument();
  });

  it("lists what an unsubmitted campaign still needs before review (D38d)", () => {
    const { rerender } = render(
      <CampaignPreparationSummary
        campaign={campaign}
        commercial={commercial}
        creatives={[]}
        targetAreas={0}
      />,
    );
    expect(
      screen.getByText(
        "Before you can submit for review, add start and end dates, a total budget and a target area.",
      ),
    ).toBeInTheDocument();

    const complete = {
      ...campaign,
      start_at: "2026-10-01T08:00:00Z",
      end_at: "2026-10-31T17:00:00Z",
      budget_amount: "5000.00",
    } as Campaign;
    rerender(
      <CampaignPreparationSummary
        campaign={complete}
        commercial={commercial}
        creatives={[]}
        targetAreas={1}
      />,
    );
    expect(screen.queryByText(/Before you can submit/)).not.toBeInTheDocument();

    // An unreadable area count is not reported as missing; submitted campaigns show nothing.
    rerender(
      <CampaignPreparationSummary
        campaign={{ ...complete, budget_amount: "0" } as Campaign}
        commercial={commercial}
        creatives={[]}
      />,
    );
    expect(
      screen.getByText("Before you can submit for review, add a total budget."),
    ).toBeInTheDocument();
    rerender(
      <CampaignPreparationSummary
        campaign={{ ...campaign, status: "pending_review" } as Campaign}
        commercial={commercial}
        creatives={[]}
        targetAreas={0}
      />,
    );
    expect(screen.queryByText(/Before you can submit/)).not.toBeInTheDocument();
  });

  it("withholds a readiness conclusion when one source is unavailable", () => {
    render(<CampaignPreparationSummary campaign={campaign} commercial={commercial} />);
    expect(screen.getByText(/not showing a readiness conclusion/)).toBeInTheDocument();
    expect(screen.queryByText(/ready to launch/i)).not.toBeInTheDocument();
  });

  it("withholds a readiness conclusion when commercial facts are unavailable", () => {
    render(<CampaignPreparationSummary campaign={campaign} creatives={[]} />);
    expect(screen.getByText(/not showing a readiness conclusion/)).toBeInTheDocument();
    expect(screen.queryByText(/Next action:/)).not.toBeInTheDocument();
  });

  const accepted = {
    quote_request: { id: "q1" },
    revisions: [{ id: "r1" }],
    terms: { id: "t1" },
    financial_authority: null,
  } as unknown as Commercial;
  const funded = { ...accepted, financial_authority: { id: "fa1" } } as unknown as Commercial;
  const approved = [{ status: "approved" } as Creative];

  function fact(label: string) {
    return screen.getByText(label, { selector: "dt" }).nextElementSibling;
  }

  it.each([
    {
      name: "a rejected campaign",
      status: "rejected",
      facts: accepted,
      creatives: approved,
      action: "Update the rejected campaign details, then resubmit.",
      quote: "Accepted",
      artwork: "Approved",
    },
    {
      name: "a requested quotation not yet posted",
      status: "draft",
      facts: { ...commercial, quote_request: { id: "q1" } } as unknown as Commercial,
      creatives: [],
      action: "Wait for Terrax Media to post the quotation for review.",
      quote: "Being prepared",
      artwork: "Not added",
    },
    {
      name: "a posted quotation awaiting acceptance",
      status: "draft",
      facts: { ...accepted, terms: null } as unknown as Commercial,
      creatives: [],
      action: "Review and accept the latest quotation shown below.",
      quote: "Review required",
      artwork: "Not added",
    },
    {
      name: "accepted terms without artwork",
      status: "draft",
      facts: accepted,
      creatives: [],
      action: "Add the artwork files required for this campaign.",
      quote: "Accepted",
      artwork: "Not added",
    },
    {
      name: "draft artwork",
      status: "draft",
      facts: accepted,
      creatives: [{ status: "approved" }, { status: "draft" }] as Creative[],
      action: "Submit each draft artwork file for Terrax Media to review.",
      quote: "Accepted",
      artwork: "Submit for review",
    },
    {
      name: "artwork under review",
      status: "draft",
      facts: accepted,
      creatives: [{ status: "pending_review" }] as Creative[],
      action: "Wait for Terrax Media to finish the artwork review.",
      quote: "Accepted",
      artwork: "Under review",
    },
    {
      name: "approved artwork without funding authority",
      status: "draft",
      facts: accepted,
      creatives: approved,
      action: "Wait for Terrax Media to confirm your payment or agreed credit.",
      quote: "Accepted",
      artwork: "Approved",
    },
    {
      name: "artwork in a status that is not yet reviewable",
      status: "draft",
      facts: funded,
      creatives: [{ status: "approved" }, { status: "archived" }] as Creative[],
      action: "Submit the completed campaign for Terrax Media to review.",
      quote: "Accepted",
      artwork: "Not ready",
    },
  ])("names one next action for $name", ({ status, facts, creatives, action, quote, artwork }) => {
    render(
      <CampaignPreparationSummary
        campaign={{ ...campaign, status } as Campaign}
        commercial={facts}
        creatives={creatives}
      />,
    );
    expect(screen.getByText(`Next action: ${action}`)).toBeInTheDocument();
    expect(fact("Quotation")).toHaveTextContent(quote);
    expect(fact("Artwork")).toHaveTextContent(artwork);
  });

  it.each([
    [
      "pending_review",
      "Wait for Terrax Media to finish the campaign review.",
      "Pending review",
      false,
    ],
    [
      "active",
      "This campaign is live. Results appear on the Campaign Performance Analysis page once Terrax Media issues a report.",
      "Live",
      true,
    ],
    ["paused", "This campaign is paused. Terrax Media decides when it can resume.", "Paused", true],
    [
      "completed",
      "This campaign has finished. Its report appears on the Campaign Performance Analysis page once issued.",
      "Completed",
      true,
    ],
    ["cancelled", "This campaign is cancelled; no new work can start.", "Cancelled", true],
    [
      "approved",
      "Terrax Media now arranges drivers, installation and the start date.",
      "Approved",
      false,
    ],
  ])(
    "reports the recorded %s campaign lifecycle once preparation facts are complete",
    (status, action, review, lifecycle) => {
      render(
        <CampaignPreparationSummary
          campaign={{ ...campaign, status } as Campaign}
          commercial={funded}
          creatives={approved}
        />,
      );
      expect(screen.getByText(`Next action: ${action}`)).toBeInTheDocument();
      expect(fact("Campaign review")).toHaveTextContent(review);
      expect(fact("Funding / credit")).toHaveTextContent("Recorded");
      if (lifecycle) {
        expect(screen.getAllByText(review)).toHaveLength(2);
        expect(screen.queryByText("Preparation in progress")).not.toBeInTheDocument();
      } else {
        expect(screen.getByText("Preparation in progress")).toHaveClass("text-amber");
      }
    },
  );

  it.each(["active", "completed"])(
    "does not ask for a quotation on a %s campaign recorded without one",
    (status) => {
      render(
        <CampaignPreparationSummary
          campaign={{ ...campaign, status } as Campaign}
          commercial={commercial}
          creatives={[]}
        />,
      );
      expect(screen.queryByText(/Request the custom quotation/)).not.toBeInTheDocument();
      expect(fact("Quotation")).toHaveTextContent("Not requested");
    },
  );
});
