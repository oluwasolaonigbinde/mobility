import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CampaignWizard } from "./wizard";
import { createCampaignAction } from "./actions";
vi.mock("./actions", () => ({ createCampaignAction: vi.fn() }));
const id = "00000000-0000-4000-8000-00000000000a";
beforeEach(() => {
  window.history.replaceState(null, "", "/advertiser/campaigns/new");
  vi.mocked(createCampaignAction)
    .mockReset()
    .mockResolvedValue({ error: "Attachment failed", createdCampaignId: id });
});
it("turns a partial creation into an attachment retry with a reload-safe target", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Already created");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Create campaign" }));
  await screen.findByRole("alert");
  expect(window.location.search).toBe(`?campaignId=${id}`);
  expect(screen.queryByRole("button", { name: "Create campaign" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Attach creatives" }));
  await waitFor(() => expect(createCampaignAction).toHaveBeenLastCalledWith(expect.anything(), id));
});
it("reload recovery opens only creative editing for the existing campaign", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" existingCampaign={{ id, name: "Already created" }} />);
  expect(screen.getByRole("button", { name: "+ Add creative" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Campaign name *")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "← Back" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Attach creatives" }));
  await waitFor(() => expect(createCampaignAction).toHaveBeenCalledWith(expect.anything(), id));
});
