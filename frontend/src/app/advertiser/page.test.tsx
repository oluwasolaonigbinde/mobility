import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
  isAdvertiserViewer: (me: { advertiser_organization?: { membership_role?: string } }) =>
    me.advertiser_organization?.membership_role === "viewer",
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
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
  start_at: null,
  end_at: null,
  preview_file_id: "file-one",
  target_zone_count: 2,
  budget_used: {
    amount: "200.00",
    budget_amount: "1000.00",
    currency: "NGN",
    basis: "funding",
    as_of: "2026-10-18T10:00:00Z",
  },
};
function ready(path: string) {
  if (path.endsWith("dashboard/summary"))
    return {
      data: {
        assignments: { active: 8 },
        costs: { totals_by_currency: [{ final_payout_total: "123456" }] },
      },
    };
  if (path.endsWith("/campaigns")) return { data: { items: [campaign], total: 1 } };
  return { data: { items: [], total: 0 } };
}
const figures = () => screen.getByLabelText("Running campaign figures");
beforeEach(() => {
  mocks.get.mockReset().mockImplementation(async (path: string) => ready(path));
  mocks.role.mockResolvedValue({
    user: { full_name: "Ada", role: "advertiser" },
    advertiser_organization: { name: "Marula", membership_role: "owner", currency: "NGN" },
  });
});
it("shows the two running figures, no booked total and one running card", async () => {
  render(await Home());
  for (const name of ["Running campaigns", "Cars on the road"])
    expect(screen.getByText(name)).toBeInTheDocument();
  expect(figures()).toHaveTextContent("Running campaigns1");
  expect(figures()).toHaveTextContent("Cars on the road8");
  // Booked is one campaign's figure (D103); Home never adds it up across campaigns.
  expect(document.body).not.toHaveTextContent(/booked|₦200\.00|budget/i);
  expect(mocks.get).not.toHaveBeenCalledWith(
    "/api/v1/advertiser/campaigns/{campaign_id}/commercial",
    expect.anything(),
  );
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome back, Marula");
  expect(screen.getByText("1 campaign is on the road right now.")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/on the move|in one place/i);
  expect(screen.getAllByRole("link", { name: /Start a new campaign/ })).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Marula Kitchens" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one",
  );
  expect(screen.getByRole("link", { name: /Start a new campaign/ })).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(
    /driver pay|123,456|estimated ad exposure|fraud flags/i,
  );
});
it("builds each card from the list read alone", async () => {
  const { container } = render(await Home());
  expect(screen.getByText("2 target areas")).toBeInTheDocument();
  expect(container.querySelector("img[src*='/api/advertiser/artwork/file-one']")).not.toBeNull();
  expect(mocks.get.mock.calls.map(([path]) => path).sort()).toEqual([
    "/api/v1/advertiser/campaigns",
    "/api/v1/advertiser/dashboard/summary",
  ]);
});
it("retains campaign inventory when aggregate metrics fail", async () => {
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("dashboard/summary"))
      throw new ApiError(503, { code: "DOWN", message: "Private failure" });
    return ready(path);
  });
  render(await Home());
  expect(screen.getByRole("link", { name: campaign.name })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Campaign results unavailable" })).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("Private failure");
});
it("does not replace an inventory failure with an empty state or financial zero", async () => {
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/campaigns"))
      throw new ApiError(503, { code: "DOWN", message: "Private failure" });
    return ready(path);
  });
  render(await Home());
  expect(screen.getByRole("heading", { name: "Campaigns unavailable" })).toBeInTheDocument();
  expect(screen.queryByText("No campaigns running")).toBeNull();
  expect(figures()).toHaveTextContent("Running campaigns—");
  expect(figures()).not.toHaveTextContent(/Running campaigns0/);
});
it("shows a friendly illustrated empty state and hides create for viewers", async () => {
  mocks.role.mockResolvedValue({
    user: { full_name: "Ada" },
    advertiser_organization: { membership_role: "viewer" },
  });
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/campaigns") ? { data: { items: [], total: 0 } } : ready(path),
  );
  render(await Home());
  expect(screen.getByText("No campaigns running")).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome back, Ada");
  expect(screen.getByText("No campaigns are running right now.")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Start a new campaign/ })).toBeNull();
  expect(figures()).toHaveTextContent("Running campaigns0");
});
it("keeps one primary start action when nothing is running", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/campaigns") ? { data: { items: [], total: 0 } } : ready(path),
  );
  render(await Home());
  expect(screen.getByText("No campaigns running")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /Start a new campaign/ })).toHaveLength(1);
});
it("loads every running campaign page before presenting the count", async () => {
  mocks.get.mockImplementation(
    async (path: string, options?: { params?: { query?: { offset?: number } } }) =>
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
        : ready(path),
  );
  render(await Home());
  expect(screen.getByRole("link", { name: "Second campaign" })).toBeInTheDocument();
  expect(mocks.get).toHaveBeenCalledWith(
    "/api/v1/advertiser/campaigns",
    expect.objectContaining({ params: { query: { status: "active", limit: 100, offset: 1 } } }),
  );
  expect(figures()).toHaveTextContent("Running campaigns2");
});
it("redirects expired sessions without retaining data", async () => {
  mocks.get.mockRejectedValue(new ApiError(401, { code: "EXPIRED", message: "Expired" }));
  await expect(Home()).rejects.toThrow("redirect:/login");
});
it.each(["failed", "repeated"])(
  "withholds the complete population when later pagination is %s",
  async (failure) => {
    mocks.get.mockImplementation(
      async (path: string, options?: { params?: { query?: { offset?: number } } }) => {
        if (!path.endsWith("/campaigns")) return ready(path);
        if (options?.params?.query?.offset && failure === "failed")
          throw new ApiError(503, { code: "DOWN", message: "Private failure" });
        return { data: { items: [campaign], total: 2 } };
      },
    );
    render(await Home());
    expect(screen.getByRole("heading", { name: "Campaigns unavailable" })).toBeInTheDocument();
    expect(figures()).toHaveTextContent("Running campaigns—");
  },
);
