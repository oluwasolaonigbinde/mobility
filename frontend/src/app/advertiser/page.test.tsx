import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/components/campaigns/campaign-map", () => ({
  CampaignMap: () => <div>Actual campaign map</div>,
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
import Home from "./page";
const campaign = {
  id: "one",
  name: "Marula Kitchens",
  status: "active",
  currency: "NGN",
  budget_amount: "1000.00",
  start_at: "2026-10-01T08:00Z",
  end_at: "2026-10-30T18:00Z",
  preview_file_id: "file-one",
  target_zone_count: 2,
  budget_used: { amount: "200.00" },
};
type Options = { params?: { path?: { campaign_id?: string }; query?: { offset?: number } } };
function ready(path: string, options?: Options) {
  const id = options?.params?.path?.campaign_id ?? "one";
  if (path.endsWith("/campaigns")) return { data: { items: [campaign], total: 1 } };
  if (path.endsWith("/live-positions"))
    return {
      data: {
        campaign_id: id,
        delay_minutes: 15,
        positions: [{ longitude: 7.49, latitude: 9.06 }],
      },
    };
  if (path.endsWith("/report"))
    return {
      data: {
        campaign_id: id,
        start_at: campaign.start_at,
        end_at: campaign.end_at,
        totals: { estimated_views: "12500" },
      },
    };
  if (path.endsWith("/qr-scans")) return { data: { campaign_id: id, scans: 3, days: [] } };
  if (path.endsWith("/daily-metrics"))
    return {
      data: { campaign_id: id, items: [{ date: "2026-10-20", distance_m: "25000" }], total: 1 },
    };
  return { data: { items: [], total: 0 } };
}
const figures = () => screen.getByLabelText("Running campaign figures");
beforeEach(() => {
  vi.setSystemTime(new Date("2026-10-20T12:00Z"));
  mocks.get
    .mockReset()
    .mockImplementation(async (path: string, options?: Options) => ready(path, options));
  mocks.role.mockResolvedValue({
    user: { full_name: "Ada", role: "advertiser" },
    advertiser_organization: { name: "Marula", membership_role: "advertiser" },
  });
});
it("has the approved hero, actual artwork/map, estimates and no Home money total", async () => {
  const { container } = render(await Home());
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome back, Marula");
  expect(figures()).toHaveTextContent("Running campaigns1");
  expect(figures()).toHaveTextContent("Cars on the road1");
  expect(document.body).not.toHaveTextContent(
    /booked|₦200|budget|driver pay|CTR|ROI|website visits/i,
  );
  expect(screen.getByText("Actual campaign map")).toBeInTheDocument();
  expect(screen.getByText("Estimated views")).toBeInTheDocument();
  expect(screen.getByText("12,500")).toBeInTheDocument();
  expect(screen.getByText("QR scans")).toBeInTheDocument();
  expect(screen.getByText("Day 20 of 30")).toBeInTheDocument();
  expect(container.querySelector(".portal-hero-art")).not.toBeNull();
  expect(container.querySelector("img[src*='/api/advertiser/artwork/file-one']")).not.toBeNull();
  expect(container.querySelectorAll("a.brand-action")).toHaveLength(1);
  expect(mocks.get.mock.calls.some(([path]) => path.endsWith("/commercial"))).toBe(false);
});
it("keeps campaign inventory and unavailable figures when result reads fail", async () => {
  mocks.get.mockImplementation(async (path: string, options?: Options) => {
    if (path.endsWith("/live-positions") || path.endsWith("/report"))
      throw new ApiError(503, { code: "DOWN", message: "Private failure" });
    return ready(path, options);
  });
  render(await Home());
  expect(screen.getByRole("link", { name: campaign.name })).toBeInTheDocument();
  expect(figures()).toHaveTextContent("Cars on the road—");
  expect(screen.getByText(/Some performance figures couldn't be loaded/)).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("Private failure");
});
it("does not disguise an inventory failure as empty or zero", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "DOWN", message: "private" }));
  render(await Home());
  expect(screen.getByRole("heading", { name: "Campaigns unavailable" })).toBeInTheDocument();
  expect(screen.queryByText("No campaigns yet")).toBeNull();
  expect(figures()).toHaveTextContent("Running campaigns—");
});
it("welcomes a new advertiser with zeros and exactly one start action", async () => {
  mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
  const { container } = render(await Home());
  expect(screen.getByText("No campaigns yet")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "Welcome to Cardvert, Marula",
  );
  expect(figures()).toHaveTextContent("Cars on the road0");
  expect(screen.getAllByRole("link", { name: /Start your first campaign/ })).toHaveLength(1);
  expect(container.querySelectorAll("a.brand-action")).toHaveLength(1);
});
it("does not call an account with a draft brand new", async () => {
  mocks.get.mockResolvedValue({ data: { items: [{ ...campaign, status: "draft" }], total: 1 } });
  render(await Home());
  expect(screen.getByText("No campaigns running")).toBeInTheDocument();
  expect(screen.queryByText("No campaigns yet")).toBeNull();
});
it("loads every owned campaign without campaign, car or time selectors", async () => {
  mocks.get.mockImplementation(async (path: string, options?: Options) =>
    path.endsWith("/campaigns")
      ? {
          data: {
            items: [
              options?.params?.query?.offset
                ? { ...campaign, id: "two", name: "Second campaign" }
                : campaign,
            ],
            total: 2,
          },
        }
      : ready(path, options),
  );
  render(await Home());
  expect(figures()).toHaveTextContent("Running campaigns2");
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByRole("link", { name: "Second campaign" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: campaign.name })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Show campaign" })).toBeNull();
  expect(mocks.get.mock.calls.filter(([path]) => path.endsWith("/live-positions"))).toEqual([
    [
      "/api/v1/advertiser/campaigns/{campaign_id}/live-positions",
      { params: { path: { campaign_id: "one" } } },
    ],
    [
      "/api/v1/advertiser/campaigns/{campaign_id}/live-positions",
      { params: { path: { campaign_id: "two" } } },
    ],
  ]);
});
it("shows the required empty driving state for a campaign with no eligible delayed positions", async () => {
  mocks.get.mockImplementation(async (path: string, options?: Options) =>
    path.endsWith("/live-positions")
      ? { data: { campaign_id: "one", delay_minutes: 15, positions: [] } }
      : ready(path, options),
  );
  render(await Home());
  expect(screen.getByText("No cars driving right now")).toBeInTheDocument();
  expect(figures()).toHaveTextContent("Cars on the road0");
});
