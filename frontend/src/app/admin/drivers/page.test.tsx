import { render, screen } from "@testing-library/react";
import { beforeEach, it, expect, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
import DriversPage from "./page";
beforeEach(() => get.mockReset());
it("uses one combined applicants search and preserves each actual identity", async () => {
  get.mockResolvedValue({
    data: {
      applicants: [
        {
          id: "app",
          kind: "application",
          application_id: "app",
          driver_profile_id: "driver",
          full_name: "Ada",
        },
        { id: "staff", kind: "staff_added", driver_profile_id: "staff", full_name: "Bola" },
      ],
      total: 2,
    },
  });
  render(await DriversPage({ searchParams: Promise.resolve({ q: "0803" }) }));
  expect(get).toHaveBeenCalledTimes(1);
  expect(get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
    params: { query: { q: "0803", limit: 25, offset: 0, include_staff_added: true } },
  });
  expect(screen.getAllByRole("search")).toHaveLength(1);
  expect(screen.getByRole("link", { name: /Bola/ })).toHaveAttribute(
    "href",
    "/admin/drivers/staff",
  );
  expect(screen.getByRole("link", { name: /Ada/ })).toHaveAttribute(
    "href",
    "/admin/drivers/driver?application=app",
  );
});
it("does not claim no waiting applicants when an old page is empty", async () => {
  get.mockResolvedValue({ data: { applicants: [], total: 2 } });
  render(await DriversPage({ searchParams: Promise.resolve({ offset: "25" }) }));
  expect(screen.getByText("No applicants on this page.")).toBeVisible();
  expect(screen.queryByText("No applicants waiting.")).toBeNull();
});
