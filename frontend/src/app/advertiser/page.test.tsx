import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const { get, requireRole } = vi.hoisted(() => ({
  get: vi.fn(),
  requireRole: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
import AdvertiserOverviewPage from "./page";
const campaign = {
  id: "campaign-1",
  name: "Healthy inventory",
  organization_id: "org-1",
  status: "draft",
  metadata: { demo: true },
};
const summary = {
  costs: { totals_by_currency: [] },
  quality: { fraud_flags: { open: 0 } },
  impressions: {
    estimated_impressions: "123",
    estimated_trip_count: 2,
    average_confidence_score: "0.8",
  },
  campaigns: { active: 1, total: 1 },
  assignments: { active: 1 },
  trips: { total: 2 },
};
const fail = (status = 503, code = "PRIVACY_LIVE_USE_BLOCKED") =>
  new ApiError(status, { code, message: "Sensitive failure" });

describe("resilient advertiser overview", () => {
  beforeEach(() => {
    requireRole.mockResolvedValue({
      user: { role: "advertiser", email: "demo@example.com", full_name: "Ada" },
      advertiser_organization: { id: "org-1", name: "Healthy company" },
    });
    get.mockReset().mockImplementation(async (path: string) => ({
      data: path.endsWith("/summary") ? summary : { items: [campaign], total: 1 },
    }));
  });
  it("keeps healthy inventory when gated metrics are unavailable", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/summary")) throw fail();
      return { data: { items: [campaign], total: 1 } };
    });
    render(await AdvertiserOverviewPage());
    expect(screen.getByRole("link", { name: campaign.name })).toHaveAttribute(
      "href",
      "/advertiser/campaigns/campaign-1",
    );
    expect(
      screen.getByRole("heading", { name: "Campaign results unavailable" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Open fraud flags")).not.toBeInTheDocument();
    expect(screen.queryByText("Estimated ad exposure")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Sensitive failure");
  });
  it("keeps actual metrics when inventory fails without inventing empty inventory", async () => {
    get.mockImplementation(async (path: string) => {
      if (!path.endsWith("/summary")) throw fail(503, "DOWN");
      return { data: summary };
    });
    render(await AdvertiserOverviewPage());
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Campaigns unavailable" })).toBeInTheDocument();
    expect(screen.queryByText("No campaigns yet.")).not.toBeInTheDocument();
  });
  it("preserves successful empty inventory", async () => {
    get.mockImplementation(async (path: string) => ({
      data: path.endsWith("/summary") ? summary : { items: [], total: 0 },
    }));
    render(await AdvertiserOverviewPage());
    expect(screen.getByText("No campaigns yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all 0 campaigns →" })).toBeInTheDocument();
  });
  it.each(["/summary", "/campaigns"])(
    "redirects later401 during %s instead of retaining page data",
    async (suffix) => {
      get.mockImplementation(async (path: string) => {
        if (path.endsWith(suffix)) throw fail(401, "EXPIRED");
        return { data: path.endsWith("/summary") ? summary : { items: [campaign], total: 1 } };
      });
      await expect(AdvertiserOverviewPage()).rejects.toThrow("redirect:/login");
    },
  );
  it("presents demo-tagged records as ordinary campaigns", async () => {
    render(await AdvertiserOverviewPage());
    expect(screen.getByRole("link", { name: campaign.name })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent campaigns" })).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/demo|synthetic/i);
  });
  it("labels measured and modelled results in plain language", async () => {
    render(await AdvertiserOverviewPage());
    expect(screen.getByText("Estimated ad exposure")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Estimated opportunities to see the ad, based on routes and traffic. This is not a count of people or measured views.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Driver pay to date")).toBeInTheDocument();
    expect(
      screen.getByText("Calculated driver pay; your invoice is shown in Billing."),
    ).toBeInTheDocument();
    expect(screen.getByText("Trip integrity checks awaiting Cardvert review")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(
      /potential contacts|confidence|diagnostic|aggregate measurement|billable inventory/i,
    );
  });
});
