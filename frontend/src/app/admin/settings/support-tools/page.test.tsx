import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../../search-select", () => ({ SearchSelect: () => <input aria-label="Find driver" /> }));
vi.mock("../../payouts/process-trip-form", () => ({
  ProcessTripForm: ({ tripId }: { tripId: string }) => <button>Recalculate {tripId}</button>,
}));
vi.mock("../../hub-drawer", () => ({
  HubDrawer: ({ children, closeHref }: { children: ReactNode; closeHref: string }) => (
    <section>
      <a href={closeHref}>Close</a>
      {children}
    </section>
  ),
}));
import SupportTools from "./page";
const rows = Array.from({ length: 101 }, (_, index) => ({
  id: `calculation-${index}`,
  trip_session_id: `trip-${index}`,
  driver_profile_id: "driver",
  trip_started_at: "2026-09-03T07:15:00Z",
  campaign_name: "PalmPay Wuse",
}));
beforeEach(() => {
  get.mockReset();
  get.mockImplementation(async (_path, options) => {
    const query = options.params.query;
    return { data: { items: rows.slice(query.offset, query.offset + query.limit), total: 101 } };
  });
});
it("opens a named trip beyond the visible page without accepting a typed trip ID", async () => {
  render(
    await SupportTools({
      searchParams: Promise.resolve({
        driver_profile_id: "driver",
        trip: "trip-100",
        offset: "25",
      }),
    }),
  );
  expect(screen.getByRole("button", { name: "Recalculate trip-100" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
    "href",
    "/admin/settings/support-tools?driver_profile_id=driver&offset=25",
  );
  expect(
    get.mock.calls.every(([, options]) => options.params.query.driver_profile_id === "driver"),
  ).toBe(true);
});
it("does not offer recalculation when the selected trip belongs to another driver", async () => {
  get.mockResolvedValue({
    data: { items: [{ ...rows[0], driver_profile_id: "other" }], total: 1 },
  });
  render(
    await SupportTools({
      searchParams: Promise.resolve({ driver_profile_id: "driver", trip: "trip-0" }),
    }),
  );
  expect(screen.getByText("Trip not found for this driver.")).toBeVisible();
  expect(screen.queryByRole("button", { name: /Recalculate/ })).toBeNull();
});
it("reports a failed read without a recalculation control", async () => {
  get.mockRejectedValue(new Error("Unavailable"));
  render(
    await SupportTools({
      searchParams: Promise.resolve({ driver_profile_id: "driver", trip: "trip-0" }),
    }),
  );
  expect(
    screen
      .getAllByRole("alert")
      .every((section) => section.textContent === "Couldn't load this section — try again"),
  ).toBe(true);
  expect(screen.queryByRole("button", { name: /Recalculate/ })).toBeNull();
});
