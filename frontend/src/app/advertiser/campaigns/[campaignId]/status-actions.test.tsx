import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./actions", () => ({ submitCampaignForReviewAction: vi.fn() }));

import { StatusActions } from "./status-actions";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const EDIT_HREF = `/advertiser/campaigns/${CAMPAIGN_ID}/edit`;

describe("StatusActions", () => {
  it("lets a rejected campaign reach the edit form it tells the advertiser to use", () => {
    render(<StatusActions campaignId={CAMPAIGN_ID} status="rejected" />);

    expect(screen.getByRole("link", { name: "Edit details" })).toHaveAttribute("href", EDIT_HREF);
    expect(screen.getByRole("link", { name: "edit the details" })).toHaveAttribute(
      "href",
      EDIT_HREF,
    );
    expect(screen.getByRole("button", { name: "Resubmit for review" })).toBeInTheDocument();
  });

  it("offers editing for a draft", () => {
    render(<StatusActions campaignId={CAMPAIGN_ID} status="draft" />);

    expect(screen.getByRole("link", { name: "Edit details" })).toHaveAttribute("href", EDIT_HREF);
  });

  it.each(["pending_review", "approved"] as const)("offers no edit link while %s", (status) => {
    render(<StatusActions campaignId={CAMPAIGN_ID} status={status} />);

    expect(screen.queryByRole("link", { name: "Edit details" })).not.toBeInTheDocument();
  });
});
