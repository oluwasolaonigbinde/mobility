import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ read: vi.fn(), get: vi.fn(), drawing: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/api/audit-batch2", () => ({ readCampaignPerformance: mocks.read }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not-found");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("@/components/campaigns/area-graphic", () => ({
  AreaGraphic: (props: unknown) => {
    mocks.drawing(props);
    return <p>Drawn campaign area</p>;
  },
}));
import CampaignMapPage from "./page";
const campaignId = "00000000-0000-4000-8000-000000000001";
const area = { id: "area", campaign_id: campaignId, name: "Chosen area" };
const report = {
  campaign_id: campaignId,
  areas: [],
  completeness: "Current campaign results",
  uncertainty: "Estimated views",
};
const page = () => CampaignMapPage({ params: Promise.resolve({ campaignId }) });
beforeEach(() => {
  vi.resetAllMocks();
  mocks.get.mockResolvedValue({ data: { items: [area], total: 1 } });
  mocks.read.mockResolvedValue({ data: report });
});
it("keeps chosen geometry separate from an empty safe performance breakdown", async () => {
  const { container } = render(await page());
  expect(screen.getByText("Drawn campaign area")).toBeInTheDocument();
  expect(screen.getByText(/Area results aren’t available/)).toBeInTheDocument();
  expect(mocks.drawing).toHaveBeenCalledWith({ areas: [area] });
  expect(
    mocks.get.mock.calls.every(
      (call) => call[0] === "/api/v1/advertiser/campaigns/{campaign_id}/zones",
    ),
  ).toBe(true);
  expect(container).not.toHaveTextContent(/rank|heatmap|disclosure|synthetic|basemap|calibration/i);
});
it("shows only the returned safe area names, independent of geometry position", async () => {
  mocks.read.mockResolvedValue({
    data: {
      ...report,
      areas: [
        {
          area_id: "safe-other-id",
          name: "Safe area name",
          trip_count: 3,
          modelled_potential_contacts: "120",
        },
      ],
    },
  });
  render(await page());
  expect(screen.getByRole("rowheader", { name: "Safe area name" })).toBeInTheDocument();
});
it("does not draw foreign geometry or claim it is empty", async () => {
  mocks.get.mockResolvedValue({ data: { items: [{ ...area, campaign_id: "other" }], total: 1 } });
  render(await page());
  expect(screen.getByRole("status", { name: "Area picture unavailable" })).toBeInTheDocument();
  expect(mocks.drawing).not.toHaveBeenCalled();
  expect(screen.queryByText(/No campaign areas have been chosen/)).toBeNull();
});
it("retains the chosen area when performance is temporarily unavailable", async () => {
  mocks.read.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "private" }));
  render(await page());
  expect(screen.getByText("Drawn campaign area")).toBeInTheDocument();
  expect(screen.getByRole("status", { name: "Area results unavailable" })).toBeInTheDocument();
});
it("rejects a foreign campaign report", async () => {
  mocks.read.mockResolvedValue({ data: { ...report, campaign_id: "other" } });
  await expect(page()).rejects.toThrow("not-found");
});
