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

  it("withholds a readiness conclusion when one source is unavailable", () => {
    render(<CampaignPreparationSummary campaign={campaign} commercial={commercial} />);
    expect(screen.getByText(/not showing a readiness conclusion/)).toBeInTheDocument();
    expect(screen.queryByText(/ready to launch/i)).not.toBeInTheDocument();
  });
});
