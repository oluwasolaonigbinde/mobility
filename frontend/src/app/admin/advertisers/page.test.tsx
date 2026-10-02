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
  get.mockResolvedValue({
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
  });
  render(await AdvertisersPage({ searchParams: Promise.resolve({ q: "Palm", offset: "25" }) }));
  expect(get).toHaveBeenCalledWith("/api/v1/admin/advertiser-organizations", {
    params: { query: { q: "Palm", limit: 25, offset: 25 } },
  });
  expect(screen.getByRole("link", { name: /PalmPay accounts/ })).toHaveAttribute(
    "href",
    "/admin/advertisers/company",
  );
  expect(screen.queryByRole("link", { name: "Add company" })).toBeNull();
  expect(get).toHaveBeenCalledOnce();
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
