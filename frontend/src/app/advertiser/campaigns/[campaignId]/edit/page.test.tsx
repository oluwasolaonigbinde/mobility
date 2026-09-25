import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const { get, notFound } = vi.hoisted(() => ({
  get: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("notFound");
  }),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: vi.fn(async () => ({})) }));
vi.mock("next/navigation", () => ({ notFound, redirect: vi.fn() }));
vi.mock("../actions", () => ({ updateCampaignDetailsAction: vi.fn() }));

import EditCampaignPage from "./page";

const CAMPAIGN_ID = "00000000-0000-4000-8000-00000000000a";
const campaign = {
  id: CAMPAIGN_ID,
  name: "Launch",
  description: null,
  status: "rejected",
  currency: "NGN",
  start_at: "2026-10-01T08:00:00Z",
  end_at: null,
  budget_amount: "500000.00",
  daily_budget_amount: null,
};
const input = { params: Promise.resolve({ campaignId: CAMPAIGN_ID }) };

describe("EditCampaignPage", () => {
  beforeEach(() => {
    get.mockReset();
    notFound.mockClear();
  });

  it("prefills a rejected campaign with Lagos wall-clock times and its originals", async () => {
    get.mockResolvedValue({ data: campaign });
    const { container } = render(await EditCampaignPage(input));

    expect(screen.getByLabelText("Campaign name")).toHaveValue("Launch");
    expect(screen.getByLabelText("Starts (Lagos time)")).toHaveValue("2026-10-01T09:00");
    expect(screen.getByLabelText("Ends (Lagos time)")).toHaveValue("");
    expect(screen.getByLabelText("Total budget (NGN)")).toHaveValue("500000.00");
    const original = container.querySelector<HTMLInputElement>('input[name="original_start_at"]');
    expect(original?.value).toBe("2026-10-01T09:00");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
  });

  it("explains why an approved campaign cannot be edited here", async () => {
    get.mockResolvedValue({ data: { ...campaign, status: "approved" } });
    render(await EditCampaignPage(input));

    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.getByText(/reviewed change request/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the campaign" })).toHaveAttribute(
      "href",
      `/advertiser/campaigns/${CAMPAIGN_ID}`,
    );
  });

  it("treats another company's campaign as missing", async () => {
    get.mockRejectedValue(new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "x" }));

    await expect(EditCampaignPage(input)).rejects.toThrow("notFound");
  });

  it("shows a retryable unavailable state on an operational failure", async () => {
    get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "private detail" }));
    render(await EditCampaignPage(input));

    expect(screen.getByText("Campaign unavailable")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("private detail");
  });
});
