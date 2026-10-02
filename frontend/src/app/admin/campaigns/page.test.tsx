import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
import CampaignsPage from "./page";
const campaign = {
  id: "campaign",
  name: "Wuse Blitz",
  organization: { name: "PalmPay" },
  currency: "NGN",
  budget_amount: "100000",
  status: "active",
  start_at: "2026-09-01T00:00:00Z",
  end_at: "2026-10-01T00:00:00Z",
};
beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path) => {
    if (path.endsWith("/campaigns")) return { data: { items: [campaign], total: 60 } };
    if (path.endsWith("/campaigns/{campaign_id}")) return { data: campaign };
    if (path.endsWith("/commercial"))
      return { data: { budget_evaluations: [{ billing_spend_amount: "20000" }] } };
    if (path.endsWith("/campaign-assignments")) return { data: { items: [], total: 2 } };
    return { data: { items: [], total: 0 } };
  });
});
const page = (query = {}) => CampaignsPage({ searchParams: Promise.resolve(query) });
it.each([
  ["needs-review", "pending_review", "Review campaign details"],
  ["getting-ready", "draft", "View launch checklist"],
  ["live", "paused", "Review pause and funding"],
  ["ended", "completed", "View launch checklist"],
])(
  "lists named campaigns in %s and preserves the selected work list",
  async (tab, source, next) => {
    render(await page({ tab, source, q: "Wuse", offset: "25" }));
    expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns", {
      params: { query: { status: source, q: "Wuse", limit: 25, offset: 25 } },
    });
    const row = screen.getByRole("link", { name: /Wuse Blitz PalmPay/ });
    expect(row).toHaveAttribute("href", "/admin/campaigns/campaign#overview");
    expect(row).toHaveTextContent(next);
    expect(row).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      expect.stringContaining("q=Wuse"),
    );
  },
);
it.each(["artwork", "changes", "installation"])(
  "opens %s work in its campaign section without an unsupported search",
  async (source) => {
    const normal = get.getMockImplementation()!;
    get.mockImplementation(async (path, options) => {
      if (path.endsWith("/creatives/pending-review"))
        return {
          data: {
            items: [{ creative: { id: "creative", campaign_id: "campaign", name: "Door wrap" } }],
            total: 1,
          },
        };
      if (path.endsWith("/campaign-change-requests/pending"))
        return { data: { items: [{ id: "change", campaign_id: "campaign" }] } };
      if (path.endsWith("/installation-evidence/pending"))
        return { data: { items: [{ id: "photo", assignment_id: "job", vehicle_id: "car" }] } };
      if (path.endsWith("/campaign-assignments/{assignment_id}"))
        return {
          data: {
            id: "job",
            campaign_id: "campaign",
            vehicle_id: "car",
            driver_profile: { full_name: "Ada Okafor" },
            vehicle: { plate_number: "ABC-123-XY" },
          },
        };
      return normal(path, options);
    });
    render(await page({ tab: "needs-review", source }));
    const row = screen.getByRole("link", { name: /Wuse Blitz PalmPay/ });
    expect(row).toHaveAttribute(
      "href",
      source === "installation"
        ? "/admin/campaigns/campaign?job=job#drivers"
        : `/admin/campaigns/campaign#${source === "artwork" ? "artwork" : "overview"}`,
    );
    expect(screen.queryByRole("textbox", { name: "Search this work list" })).toBeNull();
    if (source === "installation") expect(row).toHaveTextContent("Ada Okafor · ABC-123-XY");
  },
);
it.each(["artwork", "changes", "installation", "active"])(
  "does not describe failed %s reads as an empty work list",
  async (source) => {
    get.mockRejectedValue(new Error("offline"));
    render(await page({ tab: source === "active" ? "live" : "needs-review", source }));
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText(/No matching campaigns/)).toBeNull();
  },
);
it.each(["artwork", "changes", "installation"])(
  "refuses to substitute an empty list when %s parent details cannot be read",
  async (source) => {
    get.mockImplementation(async (path) => {
      if (path.endsWith("/creatives/pending-review"))
        return {
          data: { items: [{ creative: { id: "creative", campaign_id: "campaign" } }], total: 1 },
        };
      if (path.endsWith("/campaign-change-requests/pending"))
        return { data: { items: [{ id: "change", campaign_id: "campaign" }] } };
      if (path.endsWith("/installation-evidence/pending"))
        return { data: { items: [{ id: "photo", assignment_id: "job", vehicle_id: "car" }] } };
      throw new Error("parent unavailable");
    });
    render(await page({ tab: "needs-review", source }));
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Wuse Blitz/ })).toBeNull();
  },
);

it("includes paused campaigns beside live campaigns by default and keeps independent pages", async () => {
  render(await page({ tab: "live", active_offset: "25" }));
  expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns", {
    params: { query: { status: "active", q: undefined, limit: 25, offset: 25 } },
  });
  expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns", {
    params: { query: { status: "paused", q: undefined, limit: 25, offset: 0 } },
  });
  expect(screen.getAllByRole("link", { name: /Wuse Blitz PalmPay/ })).toHaveLength(2);
  expect(screen.getAllByRole("link", { name: "Next →" })[1]).toHaveAttribute(
    "href",
    "/admin/campaigns?tab=live&active_offset=25&paused_offset=25",
  );
});
it("includes all review sources by default", async () => {
  render(await page());
  for (const path of [
    "/api/v1/admin/creatives/pending-review",
    "/api/v1/admin/installation-evidence/pending",
    "/api/v1/admin/campaign-change-requests/pending",
  ])
    expect(get.mock.calls.some(([called]) => called === path)).toBe(true);
  expect(screen.getByRole("region", { name: "Campaign details" })).toBeTruthy();
});
