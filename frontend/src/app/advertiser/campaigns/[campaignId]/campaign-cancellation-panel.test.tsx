import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CampaignCancellationPanel } from "./campaign-cancellation-panel";

vi.mock("./actions", () => ({
  requestCampaignCancellationAction: vi.fn(),
}));

describe("CampaignCancellationPanel", () => {
  it("requires an explicit permanent-cutoff confirmation before enabling cancellation", async () => {
    const user = userEvent.setup();
    render(
      <CampaignCancellationPanel
        campaignId="00000000-0000-4000-8000-00000000000a"
        clientRequestId="00000000-0000-4000-8000-00000000000d"
      />,
    );

    const button = screen.getByRole("button", { name: "Cancel campaign permanently" });
    expect(button).toBeDisabled();
    expect(
      screen.getByText(/verified driver earnings before that cutoff remain payable/i),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("checkbox", {
        name: "I understand this records a permanent cancellation cutoff.",
      }),
    );
    expect(button).toBeEnabled();
  });
});
