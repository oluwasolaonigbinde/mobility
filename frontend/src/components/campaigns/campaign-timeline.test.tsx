import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { CampaignTimeline } from "./campaign-timeline";

it("lists running, scheduled and finished dates with extensions on the campaign itself", () => {
  const campaign = {
    id: "one",
    name: "Running",
    status: "active",
    start_at: "2026-10-01T10:00Z",
    end_at: "2026-11-30T10:00Z",
  };
  render(
    <CampaignTimeline
      campaigns={[
        {
          ...campaign,
          id: "later",
          name: "Scheduled",
          status: "approved",
          start_at: "2026-12-01T10:00Z",
          end_at: "2026-12-30T10:00Z",
        },
        campaign,
        {
          ...campaign,
          id: "old",
          name: "Finished",
          status: "finished",
          start_at: "2026-09-01T10:00Z",
          end_at: "2026-09-30T10:00Z",
        },
        { ...campaign, id: "draft", name: "Draft", status: "draft" },
        { ...campaign, id: "undated", name: "Undated", start_at: null },
      ]}
    />,
  );
  const timeline = screen.getByLabelText("Campaign timeline");
  expect(
    within(timeline)
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual(["Finished", "Running", "Scheduled"]);
  expect(within(timeline).getByRole("link", { name: "Running" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one",
  );
  expect(timeline).toHaveTextContent("30 Nov 2026");
  expect(within(timeline).queryByText("Draft")).toBeNull();
  expect(within(timeline).queryByText("Undated")).toBeNull();
});
it("does not invent a timeline for an empty account", () => {
  const { container } = render(<CampaignTimeline campaigns={[]} />);
  expect(container).toBeEmptyDOMElement();
});
