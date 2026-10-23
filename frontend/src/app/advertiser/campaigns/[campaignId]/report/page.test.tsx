import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({
    user: { id: "owner" },
    advertiser_organization: { id: "company" },
  }),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not-found");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("../../../reports/report-list", () => ({
  Reports: ({
    campaignId,
    campaigns,
  }: {
    campaignId: string;
    campaigns: { id: string; name: string }[];
  }) => (
    <p data-testid="reports">
      {campaignId}: {campaigns[0]?.name}
    </p>
  ),
}));
import CampaignReportPage from "./page";

beforeEach(() => {
  vi.clearAllMocks();
});
it("binds the report form to the campaign returned by the owned read", async () => {
  mocks.get.mockResolvedValue({ data: { id: "campaign", name: "Lagos launch" } });
  render(await CampaignReportPage({ params: Promise.resolve({ campaignId: "campaign" }) }));
  expect(screen.getByTestId("reports")).toHaveTextContent("campaign: Lagos launch");
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}", {
    params: { path: { campaign_id: "campaign" } },
  });
});
it("treats a foreign or missing campaign as not found", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "NOT_FOUND", message: "Not found" }));
  await expect(
    CampaignReportPage({ params: Promise.resolve({ campaignId: "foreign" }) }),
  ).rejects.toThrow("not-found");
});
it("gives an explicit retry state on an unavailable service", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "Unavailable" }));
  render(await CampaignReportPage({ params: Promise.resolve({ campaignId: "campaign" }) }));
  expect(screen.getByText("Reports unavailable")).toBeInTheDocument();
});
