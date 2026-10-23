import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ create: vi.fn(), areas: vi.fn() }));
vi.mock("./actions", () => ({ createCampaignAction: mocks.create }));
vi.mock("../[campaignId]/zones/zones-editor", () => ({
  ZonesEditor: (props: { campaignId: string }) => {
    mocks.areas(props);
    return <p>Choose areas for {props.campaignId}</p>;
  },
}));
vi.mock("@/lib/files/creative-upload", () => ({
  CREATIVE_UPLOAD_PHASE_LABELS: { clean: "File ready", scanning: "Checking file…" },
  uploadCreativeFile: vi.fn(async (_file: File, onPhase: (phase: string) => void) => {
    onPhase("clean");
    return { storedFileId: "00000000-0000-4000-8000-0000000000f1", creativeType: "image" };
  }),
}));
import { CampaignWizard } from "./wizard";
const id = "00000000-0000-4000-8000-00000000000a";
beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState(null, "", "/advertiser/campaigns/new");
  mocks.create.mockResolvedValue({ createdCampaignId: id });
});
it("saves a draft before areas, then offers design and review without auto-submitting", async () => {
  const user = userEvent.setup();
  const { container } = render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Wuse lunch rush");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(await screen.findByText(`Choose areas for ${id}`)).toBeInTheDocument();
  expect(mocks.create).toHaveBeenCalledWith(
    expect.objectContaining({
      basics: expect.objectContaining({ name: "Wuse lunch rush" }),
      creatives: [],
    }),
    undefined,
    expect.any(String),
    true,
  );
  expect(window.location.search).toBe(`?campaignId=${id}`);
  expect(screen.queryByLabelText("Campaign name *")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(screen.getByRole("button", { name: "+ Add advert design" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(screen.getByRole("heading", { name: "Review your draft" })).toBeInTheDocument();
  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(container.querySelector("form form")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Finish draft" }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(2));
  expect(mocks.create.mock.calls[1]![1]).toBe(id);
});
it("writes the recovery UUID before dispatch, freezes the payload and reuses both on an unknown retry", async () => {
  const requestId = "00000000-0000-4000-8000-00000000000b";
  mocks.create.mockImplementation(async () => {
    expect(window.location.search).toBe(`?requestId=${requestId}`);
    return { error: "Draft result unknown", campaignRequestId: requestId };
  });
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" campaignRequestId={requestId} />);
  const name = screen.getByLabelText("Campaign name *");
  await user.type(name, "Original details");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Draft result unknown");
  expect(name).toBeDisabled();
  expect(mocks.areas).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByRole("button", { name: "Continue →" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(mocks.create).toHaveBeenCalledTimes(2);
  expect(mocks.create.mock.calls[1]).toEqual(mocks.create.mock.calls[0]);
});
it("does not create twice on a pending draft save", async () => {
  let finish!: (state: { createdCampaignId: string }) => void;
  mocks.create.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Draft");
  await user.dblClick(screen.getByRole("button", { name: "Continue →" }));
  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(mocks.areas).not.toHaveBeenCalled();
  await act(async () => finish({ createdCampaignId: id }));
});
it("resumes the authorised existing draft at Areas without another create", () => {
  render(<CampaignWizard currency="NGN" existingCampaign={{ id, name: "Saved" }} />);
  expect(screen.getByText(`Choose areas for ${id}`)).toBeInTheDocument();
  expect(screen.queryByLabelText("Campaign name *")).toBeNull();
  expect(mocks.create).not.toHaveBeenCalled();
});
it("keeps exact budget strings through draft save and final review", async () => {
  const user = userEvent.setup();
  render(<CampaignWizard currency="NGN" />);
  await user.type(screen.getByLabelText("Campaign name *"), "Precise budget");
  await user.type(screen.getByLabelText("Total budget (NGN)"), "1234567.89");
  await user.type(screen.getByLabelText("Daily budget (NGN)"), "10000.00");
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await screen.findByText(`Choose areas for ${id}`);
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  await user.click(screen.getByRole("button", { name: "Continue →" }));
  expect(screen.getByText("₦1,234,567.89")).toBeInTheDocument();
  expect(mocks.create.mock.calls[0]![0].basics).toMatchObject({
    budget_amount: "1234567.89",
    daily_budget_amount: "10000.00",
  });
});
