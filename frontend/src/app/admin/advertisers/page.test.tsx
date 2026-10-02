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
it("does not attribute another company's contact to a directory row", async () => {
  get.mockImplementation(async (path) =>
    path === "/api/v1/admin/advertiser-organizations"
      ? { data: { items: [{ id: "company", name: "PalmPay", status: "active" }], total: 1 } }
      : path.endsWith("/company")
        ? { data: { id: "other", billing_contact_name: "Other contact" } }
        : { data: { items: [], total: 0 } },
  );
  render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  expect(screen.queryByText(/Other contact/)).toBeNull();
});
it("keeps all company detail reads within four concurrent requests", async () => {
  let active = 0,
    peak = 0;
  get.mockImplementation(async (path, options) => {
    active++;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, 5));
    active--;
    if (path === "/api/v1/admin/advertiser-organizations")
      return { data: { items: [{ id: "company", name: "PalmPay", status: "active" }], total: 1 } };
    if (path.endsWith("/company")) return { data: { id: "company" } };
    if (path.endsWith("/members")) return { data: { items: [], total: 0 } };
    if (path.endsWith("/campaigns"))
      return {
        data: {
          items: Array.from({ length: 8 }, (_, i) => ({
            id: `campaign${i}`,
              organization_id: "company",
            name: `Campaign ${i}`,
            status: "active",
          })),
          total: 8,
        },
      };
    if (path.endsWith("/commercial"))
      return {
        data: { campaign_id: options.params.path.campaign_id, invoices: [], settlements: [] },
      };
    return { data: { items: [], total: 0 } };
  });
  render(await AdvertisersPage({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(peak).toBe(4);
});
