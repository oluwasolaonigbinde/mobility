import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { CampaignWizard } from "./wizard";
import { createCampaignAction } from "./actions";
vi.mock("./actions", () => ({ createCampaignAction: vi.fn() }));
vi.mock("@/lib/files/creative-upload", () => ({
  uploadCreativeFile: vi.fn(async (_file: File, onPhase: (phase: string) => void) => {
    onPhase("clean");
    return { storedFileId: "00000000-0000-4000-8000-0000000000f1", creativeType: "image" };
  }),
}));
const id = "00000000-0000-4000-8000-00000000000a";
beforeEach(() => {
  window.history.replaceState(null, "", "/advertiser/campaigns/new");
  vi.mocked(createCampaignAction)
    .mockReset()
    .mockResolvedValue({ error: "Attachment failed", createdCampaignId: id });
});

async function addCreative(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "+ Add creative" }));
  await user.type(screen.getByLabelText("Creative name *"), "Full wrap");
  await user.upload(
    screen.getByLabelText("Creative file *"),
    new File(["wrap"], "wrap.png", { type: "image/png" }),
  );
  await screen.findByText(/passed security scan/);
}

it("turns a partial creation into an attachment retry with a reload-safe target", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Already created");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await addCreative(user);
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Create campaign" }));
  await screen.findByRole("alert");
  expect(window.location.search).toBe(`?campaignId=${id}`);
  // The retry button appears once the failed transition settles.
  await user.click(await screen.findByRole("button", { name: "Attach creatives" }));
  expect(screen.queryByRole("button", { name: "Create campaign" })).not.toBeInTheDocument();
  await waitFor(() =>
    expect(createCampaignAction).toHaveBeenLastCalledWith(
      expect.anything(),
      id,
      expect.any(String),
    ),
  );
});

it("reload recovery opens only creative editing for the existing campaign", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" existingCampaign={{ id, name: "Already created" }} />);
  expect(screen.getByRole("button", { name: "+ Add creative" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Campaign name *")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "← Back" })).not.toBeInTheDocument();
  await addCreative(user);
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Attach creatives" }));
  await waitFor(() =>
    expect(createCampaignAction).toHaveBeenCalledWith(expect.anything(), id, expect.any(String)),
  );
});

it("does not offer an attach action that would change nothing", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" existingCampaign={{ id, name: "Already created" }} />);
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(screen.getByRole("button", { name: "Attach creatives" })).toBeDisabled();
  expect(screen.getByText(/nothing to attach/)).toBeInTheDocument();
  expect(createCampaignAction).not.toHaveBeenCalled();
});

it("formats budget summaries while keeping the exact submitted values", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Precise budgets");
  await user.type(screen.getByLabelText("Total budget (NGN)"), "1234567.89");
  await user.type(screen.getByLabelText("Daily budget (NGN)"), "10000.00");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(screen.getByText("₦1,234,567.89")).toBeInTheDocument();
  expect(screen.getByText("₦10,000.00")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Create campaign" }));
  await waitFor(() => expect(createCampaignAction).toHaveBeenCalled());
  expect(vi.mocked(createCampaignAction).mock.calls[0]![0].basics).toMatchObject({
    budget_amount: "1234567.89",
    daily_budget_amount: "10000.00",
  });
});
