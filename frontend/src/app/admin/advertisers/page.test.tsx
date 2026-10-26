import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
import AdvertisersPage from "./page";
beforeEach(() => {
  get.mockReset();
});
it("finds named companies beyond the first page and keeps search during pagination", async () => {
  get.mockImplementation(async (path) =>
    path === "/api/v1/admin/advertiser-organizations"
      ? {
          data: {
            items: [
              {
                id: "company",
                name: "PalmPay",
                billing_email: "accounts@example.invalid",
                billing_contact_name: "Accounts",
                member_count: 1,
                live_campaign_count: 0,
                outstanding: [],
                status: "active",
              },
            ],
            total: 60,
          },
        }
      : path.endsWith("/company")
        ? {
            data: {
              id: "company",
              billing_contact_name: "Accounts",
              billing_email: "accounts@example.invalid",
            },
          }
        : path.endsWith("/members")
          ? { data: { items: [], total: 1 } }
          : { data: { items: [], total: 0 } },
  );
  render(await AdvertisersPage({ searchParams: Promise.resolve({ q: "Palm", offset: "25" }) }));
  expect(get).toHaveBeenCalledWith("/api/v1/admin/advertiser-organizations", {
    params: { query: { q: "Palm", limit: 25, offset: 25 } },
  });
  expect(screen.getByRole("link", { name: /PalmPay Accounts/ })).toHaveAttribute(
    "href",
    "/admin/advertisers/company",
  );
  expect(screen.getByRole("link", { name: "Add company" })).toHaveAttribute(
    "href",
    "/admin/advertisers/new",
  );
  expect(screen.getByRole("link", { name: "Next →" })).toHaveAttribute(
    "href",
    "/admin/advertisers?q=Palm&offset=50",
  );
});
it.each(["empty", "offline"])(
  "distinguishes an %s directory from one that could not load",
  async (state) => {
    if (state === "offline") get.mockRejectedValue(new Error("offline"));
    else get.mockResolvedValue({ data: { items: [], total: 0 } });
    render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("alert") !== null).toBe(state === "offline");
    expect(screen.queryByText("No matching companies.") !== null).toBe(state === "empty");
  },
);
it("uses the authorised row contact/counts without extra company/member reads", async () => {
  get.mockImplementation(async (path) =>
    path === "/api/v1/admin/advertiser-organizations"
      ? {
          data: {
            items: [
              {
                id: "company",
                name: "PalmPay",
                status: "active",
                member_count: 2,
                live_campaign_count: 0,
                outstanding: [],
                billing_contact_name: "Own contact",
              },
            ],
            total: 1,
          },
        }
      : path.endsWith("/company")
        ? { data: { id: "other", billing_contact_name: "Other contact" } }
        : { data: { items: [], total: 0 } },
  );
  render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByText(/Own contact/)).toBeInTheDocument();
  expect(screen.getByText("People: 2 · Live campaigns: 0")).toBeInTheDocument();
  expect(screen.queryByText(/Other contact/)).toBeNull();
  expect(
    get.mock.calls.some((call) => call[0].endsWith("/company") || call[0].endsWith("/members")),
  ).toBe(false);
});
it("shows each company's outstanding money from the list read alone", async () => {
  get.mockResolvedValue({
    data: {
      items: [
        {
          id: "company",
          name: "PalmPay",
          status: "active",
          member_count: 1,
          live_campaign_count: 8,
          outstanding: [
            { currency: "NGN", amount: "1500000.50" },
            { currency: "USD", amount: "0.00" },
          ],
        },
        {
          id: "other",
          name: "Quiet Co",
          status: "active",
          member_count: 1,
          live_campaign_count: 0,
          outstanding: [],
        },
      ],
      total: 2,
    },
  });
  render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByText("Outstanding: ₦1,500,000.50 · USD 0.00")).toBeInTheDocument();
  expect(screen.getByText("Outstanding: No issued invoices")).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(1);
});
it("does not invent zero people or live campaigns when row counts are missing", async () => {
  get.mockResolvedValue({
    data: { items: [{ id: "company", name: "PalmPay", status: "active" }], total: 1 },
  });
  render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/People: 0/)).toBeNull();
});
