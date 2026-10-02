import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const get = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
import AdminHome from "./page";
it("opens available A directories without claiming future departmental queue results", () => {
  render(<AdminHome />);
  expect(screen.getByRole("heading", { name: "Work queue" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Drivers and cars" })).toHaveAttribute(
    "href",
    "/admin/drivers",
  );
  expect(screen.getByRole("link", { name: "Campaigns" })).toHaveAttribute(
    "href",
    "/admin/campaigns",
  );
  expect(screen.getByRole("link", { name: "Companies" })).toHaveAttribute(
    "href",
    "/admin/advertisers",
  );
  expect(screen.getByRole("link", { name: "Staff logins" })).toHaveAttribute(
    "href",
    "/admin/settings/staff",
  );
  expect(screen.queryByText("Nothing waiting")).toBeNull();
  expect(
    document.querySelector(
      'a[href^="/admin/trip-checks"], a[href^="/admin/money"], a[href^="/admin/support"]',
    ),
  ).toBeNull();
  expect(get).not.toHaveBeenCalled();
});
