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
  assignment_count: 2,
  target_zone_count: 1,
  start_at: "2026-09-01T00:00:00Z",
  end_at: "2026-10-01T00:00:00Z",
};
beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (path) => {
    if (path.endsWith("/campaigns")) return { data: { items: [campaign], total: 60 } };
    if (path.endsWith("/campaigns/{campaign_id}")) return { data: campaign };
    if (path.endsWith("/commercial"))
      return { data: { budget_check: { billing_spend_amount: "20000" } } };
    if (path.endsWith("/campaign-assignments")) return { data: { items: [], total: 2 } };
    return { data: { items: [], total: 0 } };
  });
});
const page = (query = {}) => CampaignsPage({ searchParams: Promise.resolve(query) });
it.each([
  ["needs-review", "pending_review", "Review campaign details", "overview"],
  ["getting-ready", "draft", "View launch checklist", "overview"],
  ["live", "paused", "Review pause and funding", "overview"],
  ["ended", "finished", "View results", "results"],
])(
  "lists named campaigns in %s and preserves the selected work list",
  async (tab, source, next, section) => {
    render(await page({ tab, source, q: "Wuse", offset: "25" }));
    expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns", {
      params: { query: { status: source, q: "Wuse", limit: 25, offset: 25 } },
    });
    const row = screen.getByRole("link", { name: /Wuse Blitz PalmPay/ });
    expect(row).toHaveAttribute("href", `/admin/campaigns/campaign#${section}`);
    expect(row).toHaveTextContent(next);
    expect(row).toHaveTextContent("2");
    expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
      "href",
      expect.stringContaining("q=Wuse"),
    );
  },
);
it("sends a single cancelled campaign to its money summary in singular wording", async () => {
  get.mockImplementation(async (path) => {
    if (path.endsWith("/campaigns"))
      return {
        data: { items: [{ ...campaign, status: "cancelled", assignment_count: 1 }], total: 1 },
      };
    if (path.endsWith("/commercial")) return { data: { budget_check: null } };
    return { data: { items: [], total: 0 } };
  });
  render(await page({ tab: "ended", source: "cancelled" }));
  expect(get).toHaveBeenCalledWith("/api/v1/admin/campaigns", {
    params: { query: { status: "cancelled", q: undefined, limit: 25, offset: 0 } },
  });
  expect(screen.getByText("1 matching campaign")).toBeInTheDocument();
  const row = screen.getByRole("link", { name: /Wuse Blitz PalmPay/ });
  expect(row).toHaveAttribute("href", "/admin/campaigns/campaign#money");
  expect(row).toHaveTextContent("Next: See money summary");
  expect(row).toHaveTextContent("1 driver job");
  expect(row).not.toHaveTextContent("1 driver jobs");
  expect(row).not.toHaveTextContent("₦");
});
it("pluralises several matching campaigns and their driver jobs", async () => {
  render(await page({ tab: "live", source: "active" }));
  expect(screen.getByText("60 matching campaigns")).toBeInTheDocument();
  const row = screen.getByRole("link", { name: /Wuse Blitz PalmPay/ });
  expect(row).toHaveTextContent("2 driver jobs");
  expect(row).toHaveTextContent("₦20,000");
});
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

it.each([
  [
    { tab: "live", source: "active" },
    "Nothing in this list. Choose another status or change the search.",
  ],
  [{ tab: "needs-review", source: "artwork" }, "Nothing in this list. Choose another status."],
])("gates each empty-list instruction on its own control (%o)", async (query, text) => {
  get.mockImplementation(async () => ({ data: { items: [], total: 0 } }));
  render(await page(query));
  expect(screen.getByText(text)).toBeInTheDocument();
});
it("names only the controls the embedded lists show", async () => {
  get.mockImplementation(async () => ({ data: { items: [], total: 0 } }));
  render(await page({ tab: "needs-review" }));
  expect(screen.getAllByText("Nothing in this list.").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Nothing in this list. Change the search.").length).toBeGreaterThan(0);
  expect(screen.queryByText(/Choose another status/)).toBeNull();
});
it("labels ended campaigns with the decided Finished state word", async () => {
  render(await page({ tab: "ended", source: "finished" }));
  expect(screen.getByRole("link", { name: "Finished" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Completed" })).toBeNull();
});
