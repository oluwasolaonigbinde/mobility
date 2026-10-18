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
  if (path.endsWith("/commercial"))
    return {
      data: {
        budget_evaluations: [
          {
            campaign_id: "one",
            currency: "NGN",
            campaign_budget_amount: "1000.00",
            budget_basis: "total",
            billing_spend_amount: "200.00",
            evaluated_at: "2026-10-18T10:00:00Z",
            state: "within_budget",
          },
        ],
      },
    };
  return { data: { items: [], total: 0 } };
}
beforeEach(() => {
  mocks.get.mockReset().mockImplementation(async (path: string) => ready(path));
  mocks.role.mockResolvedValue({
    user: { full_name: "Ada", role: "advertiser" },
    advertiser_organization: { name: "Marula", membership_role: "owner" },
  });
});
it("shows the three useful figures, recorded spend and one running card", async () => {
  render(await Home());
  for (const name of ["Running campaigns", "Spent so far", "Cars on the road"])
    expect(screen.getByText(name)).toBeInTheDocument();
  expect(screen.getByText("₦200.00")).toBeInTheDocument();
  expect(screen.getByText("of ₦1,000.00 budget")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Marula Kitchens" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one",
  );
  expect(screen.getByRole("link", { name: /Start a new campaign/ })).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(
    /driver pay|123,456|estimated ad exposure|fraud flags/i,
  );
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
  expect(screen.queryByText("Your next big idea starts here.")).toBeNull();
  expect(screen.getByText("Spending is being updated.")).toBeInTheDocument();
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
  expect(screen.getByText("Your next big idea starts here.")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Start a new campaign/ })).toBeNull();
});
it("loads every running campaign page before presenting a total", async () => {
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
  expect(screen.getByText("Spending is being updated.")).toBeInTheDocument();
});
it("redirects expired sessions without retaining data", async () => {
  mocks.get.mockRejectedValue(new ApiError(401, { code: "EXPIRED", message: "Expired" }));
  await expect(Home()).rejects.toThrow("redirect:/login");
});
it.each(["failed", "repeated"])(
  "withholds the complete population and spend when later pagination is %s",
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
    expect(screen.queryByText("₦200.00")).toBeNull();
    expect(screen.getByText("Spending is being updated.")).toBeInTheDocument();
  },
);
it.each(["NGN", "USD"])(
  "only totals every running campaign when all currency inputs agree: %s",
  async (currency) => {
    mocks.get.mockImplementation(
      async (path: string, options?: { params?: { path?: { campaign_id?: string } } }) => {
        if (path.endsWith("/campaigns"))
          return {
            data: {
              items: [campaign, { ...campaign, id: "two", name: "Second campaign", currency }],
              total: 2,
            },
          };
        if (path.endsWith("/commercial")) {
          const id = options?.params?.path?.campaign_id;
          return {
            data: {
              budget_evaluations: [
                {
                  campaign_id: id,
                  currency: id === "two" ? currency : "NGN",
                  campaign_budget_amount: "1000.00",
                  budget_basis: "total",
                  billing_spend_amount: "200.00",
                  evaluated_at: id === "two" ? "2026-10-18T09:00:00Z" : "2026-10-18T10:00:00Z",
                  state: "within_budget",
                },
              ],
            },
          };
        }
        return ready(path);
      },
    );
    render(await Home());
    expect(screen.getByText("Across your running campaigns")).toBeInTheDocument();
    if (currency === "NGN") expect(screen.getByText("₦400.00")).toBeInTheDocument();
    else {
      expect(screen.getByText("Spending is being updated.")).toBeInTheDocument();
      expect(screen.queryByText("₦400.00")).toBeNull();
    }
  },
);
