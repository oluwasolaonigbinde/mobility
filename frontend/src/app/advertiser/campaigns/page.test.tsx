import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));

import CampaignsPage from "./page";

beforeEach(() => {
  vi.resetAllMocks();
  mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
});

it("offers campaign creation to advertisers", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("link", { name: "+ New campaign" })).toBeInTheDocument();
});

it("shows only three campaign groups and marks the selected tab", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  render(await CampaignsPage({ searchParams: Promise.resolve({ group: "setup" }) }));
  const filters = screen.getByRole("navigation", { name: "Campaign groups" });
  const current = filters.querySelectorAll('[aria-current="page"]');
  expect(current).toHaveLength(1);
  expect(current[0]).toHaveAttribute("href", "/advertiser/campaigns?group=setup");
  expect(filters.querySelectorAll("a")).toHaveLength(3);
  expect(filters.querySelector('a[href="/advertiser/campaigns"]')).not.toHaveAttribute(
    "aria-current",
  );
});
it.each([
  ["running", ["active", "paused"]],
  ["setup", ["draft", "pending_review", "approved", "rejected"]],
  ["finished", ["finished", "cancelled"]],
])("groups every campaign status under %s", async (group, expected) => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  const statuses = [
    "active",
    "paused",
    "draft",
    "pending_review",
    "approved",
    "rejected",
    "finished",
    "cancelled",
  ];
  mocks.get.mockResolvedValue({
    data: {
      items: statuses.map((status) => ({
        id: status,
        name: `Campaign ${status}`,
        status,
        currency: "NGN",
        budget_amount: "100",
        start_at: null,
        end_at: null,
      })),
      total: statuses.length,
    },
  });
  render(await CampaignsPage({ searchParams: Promise.resolve({ group: group as string }) }));
  for (const status of statuses)
    expect(screen.queryByRole("link", { name: `Campaign ${status}` }) !== null).toBe(
      (expected as string[]).includes(status),
    );
});
it("reads the complete population before applying a group filter", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  mocks.get
    .mockResolvedValueOnce({
      data: { items: [{ id: "draft", name: "Draft", status: "draft" }], total: 2 },
    })
    .mockResolvedValueOnce({
      data: {
        items: [{ id: "running", name: "Running campaign", status: "active", currency: "NGN" }],
        total: 2,
      },
    });
  render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("link", { name: "Running campaign" })).toBeInTheDocument();
  expect(mocks.get).toHaveBeenLastCalledWith("/api/v1/advertiser/campaigns", {
    params: { query: { limit: 100, offset: 1 } },
  });
});
it.each(["failed", "empty", "duplicate", "changed-total", "oversized"])(
  "does not show a partial list as complete: %s",
  async (failure) => {
    mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
    mocks.get.mockResolvedValueOnce({
      data: { items: [{ id: "one", status: "active", name: "First campaign" }], total: 2 },
    });
    if (failure === "failed")
      mocks.get.mockRejectedValueOnce(
        new ApiError(503, { code: "UNAVAILABLE", message: "offline" }),
      );
    else
      mocks.get.mockResolvedValueOnce({
        data: {
          items:
            failure === "empty"
              ? []
              : failure === "duplicate"
                ? [{ id: "one", status: "active" }]
                : failure === "oversized"
                  ? [{ id: "two" }, { id: "two" }]
                  : [{ id: "two", status: "active" }],
          total: failure === "changed-total" ? 3 : 2,
        },
      });
    render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("status", { name: "Campaigns unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "First campaign" })).toBeNull();
    expect(screen.queryByText("No campaigns yet")).toBeNull();
  },
);

it("shows each campaign's own booked figure, never a total, and a dash when it is missing", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  const used = {
    amount: "1000.00",
    budget_amount: "1000.00",
    currency: "NGN",
    basis: "invoice",
    as_of: "2026-10-18T10:00:00Z",
  };
  const row = (id: string, extra: Record<string, unknown>) => ({
    id,
    name: `Campaign ${id}`,
    status: "active",
    currency: "NGN",
    budget_amount: "1000.00",
    start_at: null,
    end_at: null,
    budget_used: used,
    ...extra,
  });
  mocks.get.mockResolvedValue({
    data: {
      items: [
        row("full", {}),
        row("daily", {
          budget_amount: null,
          budget_used: { ...used, amount: "25.00", budget_amount: null },
        }),
        row("missing", { budget_used: null }),
      ],
      total: 3,
    },
  });
  render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("columnheader", { name: "Booked" })).toBeInTheDocument();
  const cell = (id: string) =>
    screen.getByRole("link", { name: `Campaign ${id}` }).closest("tr")!.lastElementChild!;
  expect(cell("full")).toHaveTextContent(/^₦1,000\.00 of ₦1,000\.00$/);
  expect(cell("daily")).toHaveTextContent(/^₦25\.00$/);
  expect(cell("missing")).toHaveTextContent("—not available");
  expect(document.body).not.toHaveTextContent("₦1,025.00");
});
