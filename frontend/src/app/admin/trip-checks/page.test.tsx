import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../hub-drawer", () => ({
  HubDrawer: ({ children, closeHref }: { children: ReactNode; closeHref: string }) => (
    <section aria-label="Drawer">
      <a href={closeHref}>Close</a>
      {children}
    </section>
  ),
}));
vi.mock("../fraud/review-actions", () => ({ ReviewActions: () => <button>Clear</button> }));
vi.mock("../fraud/dispute-actions", () => ({
  DisputeReplyActions: () => <button>Reply to driver</button>,
}));
vi.mock("../fraud/spot-check-actions", () => ({
  SpotCheckQueueForm: () => <button>Request in-person check</button>,
  SpotCheckResultForm: () => <button>Record check</button>,
}));
vi.mock("../operation-form", () => ({ OperationForm: () => <button>Add to trip</button> }));
import TripChecks from "./page";
const date = "2026-09-03T07:15:00Z";
const flag = {
  id: "flag",
  trip_session_id: "trip",
  assignment_id: "job",
  campaign_id: "campaign",
  driver_profile_id: "driver",
  status: "open",
  description: "Top speed 250 km/h",
  detected_at: date,
  review_due_at: date,
  escalated_at: null,
  resolution_note: null,
  evidence: { max_observed_speed_mps: 70 },
  money_effect: {
    held_pending_net: "80.00",
    held_currency: "NGN",
    available_net: "90.00",
    currency: "NGN",
    reversal_recommended: false,
    reversal_entry_id: null,
  },
};
const late = {
  id: "late",
  trip_session_id: "trip",
  status: "quarantined",
  received_at: "2026-09-20T00:00:00Z",
  ping_count: 42,
};
function defaultRead(
  path: string,
  options: { params?: { path?: Record<string, string>; query?: Record<string, unknown> } },
) {
  if (path.endsWith("/analytics"))
    return {
      data: {
        trip_session_id: options.params?.path?.trip_id,
        assignment_id: "job",
        driver_profile_id: "driver",
        campaign_id: "campaign",
        started_at: date,
      },
    };
  if (path.endsWith("{assignment_id}"))
    return {
      data: {
        id: "job",
        driver_profile_id: "driver",
        campaign_id: "campaign",
        driver_profile: { full_name: "Ada Driver" },
        campaign: { name: "PalmPay Wuse" },
        vehicle: { plate_number: "ABJ-101" },
      },
    };
  if (path.endsWith("/route"))
    return {
      data: {
        flag_id: "flag",
        trip_session_id: "trip",
        items: [{ id: "point", recorded_at: date, latitude: 9, longitude: 7 }],
        total: 1,
      },
    };
  if (path.endsWith("/fraud-flags")) return { data: { items: [flag], total: 1 } };
  if (path.endsWith("/quarantined-batches")) return { data: { items: [late], total: 1 } };
  return { data: { items: [], total: 0 } };
}
const page = (query: Record<string, string> = {}) =>
  TripChecks({ searchParams: Promise.resolve(query) });
describe("Trip check work lists", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation(async (path, options) => defaultRead(path, options));
  });
  it("shows actual held pay rather than released pay and reads no locations on list loads", async () => {
    render(await page());
    expect(screen.getByRole("link", { name: /Ada Driver/ })).toHaveTextContent(/Pay held:.*80/);
    expect(screen.queryByText(/Released pay/)).toBeNull();
    expect(get.mock.calls.some(([path]) => path.endsWith("/route"))).toBe(false);
  });
  it("opens the selected trip map and keeps list filters when closing", async () => {
    render(await page({ flag: "flag", driver_profile_id: "driver", offset: "25" }));
    expect(screen.getByRole("img", { name: /Map of recorded trip locations/ })).toBeVisible();
    expect(screen.getByRole("button", { name: "Clear" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
      "href",
      "/admin/trip-checks?driver_profile_id=driver&offset=25&tab=suspicious",
    );
    expect(get).toHaveBeenCalledWith("/api/v1/admin/fraud-flags/{flag_id}/route", {
      params: { path: { flag_id: "flag" }, query: { limit: 500, offset: 0 } },
    });
  });
  it("does not draw another trip's locations", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/route")
        ? {
            data: {
              flag_id: "flag",
              trip_session_id: "other",
              items: [{ id: "x", latitude: 80, longitude: 60 }],
              total: 1,
            },
          }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag" }));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  });
  it("shows missing recorded locations honestly", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/route")
        ? { data: { flag_id: "flag", trip_session_id: "trip", items: [], total: 0 } }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag" }));
    expect(screen.getByText("No recorded locations remain for this trip.")).toBeVisible();
  });
  it("keeps overdue review evidence and pages through driver disputes", async () => {
    const disputes = Array.from({ length: 101 }, (_, index) => ({
      id: `dispute-${index}`,
      fraud_flag_id: "flag",
      driver_profile_id: "driver",
      message: `Driver explanation ${index}`,
      reply: index === 100 ? null : "Reviewed",
    }));
    get.mockImplementation(async (path, options) => {
      if (path.endsWith("/fraud-flags"))
        return { data: { items: [{ ...flag, escalated_at: date }], total: 1 } };
      if (path.endsWith("/fraud-disputes")) {
        const start = Number(options.params?.query?.offset ?? 0);
        return { data: { items: disputes.slice(start, start + 100), total: 101 } };
      }
      return defaultRead(path, options);
    });
    render(await page({ flag: "flag" }));
    expect(screen.getByText(/this review is unresolved and pay stays held/)).toBeVisible();
    expect(screen.getByRole("list", { name: "Detection evidence" })).toBeVisible();
    expect(screen.getByText("Driver explanation 100")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reply to driver" })).toBeVisible();
  });
  it("opens an existing pending check instead of asking for another", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/evidence-verifications")
        ? { data: { items: [{ id: "existing", source_trip_session_id: "trip" }], total: 1 } }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag" }));
    expect(screen.getByRole("link", { name: /In-person check waiting/ })).toHaveAttribute(
      "href",
      "/admin/trip-checks?tab=in-person&check=existing",
    );
    expect(screen.queryByRole("button", { name: "Request in-person check" })).toBeNull();
  });
  it("shows a final decision without describing pay as still held or requesting a check", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/fraud-flags")
        ? {
            data: {
              items: [
                {
                  ...flag,
                  status: "dismissed",
                  escalated_at: date,
                  resolution_note: "Driver evidence accepted",
                  money_effect: {
                    ...flag.money_effect,
                    held_pending_net: "0.00",
                    held_currency: null,
                  },
                },
              ],
              total: 1,
            },
          }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag", status: "dismissed" }));
    expect(screen.getByText("Decision: Driver evidence accepted")).toBeVisible();
    expect(screen.getByText("The review deadline passed before this decision.")).toBeVisible();
    expect(screen.queryByText(/pay stays held/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Request in-person check" })).toBeNull();
  });
  it("uses the actual trip date for late uploads and only opens scoped decisions", async () => {
    render(await page({ tab: "late", late: "late", driver_profile_id: "driver" }));
    expect(screen.getAllByText(/Trip 3 Sept 2026/)).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Add to trip" })).toBeVisible();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/trips/{trip_id}/analytics", {
      params: { path: { trip_id: "trip" } },
    });
  });
  it("hides a selected late upload outside the driver filter", async () => {
    render(await page({ tab: "late", late: "late", driver_profile_id: "other" }));
    expect(screen.getByText("Late upload not found for these filters.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add to trip" })).toBeNull();
  });
  it("includes an in-person check beyond the first hundred and opens it", async () => {
    const rows = Array.from({ length: 101 }, (_, index) => ({
      id: `check-${index}`,
      source_trip_session_id: "trip",
      assignment_id: "job",
      driver_profile_id: "driver",
      campaign_id: "campaign",
      issued_at: date,
    }));
    get.mockImplementation(async (path, options) =>
      path.endsWith("/evidence-verifications")
        ? {
            data: {
              items: rows.slice(options.params.query.offset, options.params.query.offset + 100),
              total: 101,
            },
          }
        : defaultRead(path, options),
    );
    render(await page({ tab: "in-person", check: "check-100", offset: "100" }));
    expect(screen.getByRole("button", { name: "Record check" })).toBeVisible();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/evidence-verifications", {
      params: {
        query: {
          limit: 100,
          offset: 100,
          status: "pending",
          verification_type: "physical_spot_check",
        },
      },
    });
  });
  it("never renders partial late context as a completed or empty section", async () => {
    get.mockImplementation(async (path, options) => {
      if (path.endsWith("/analytics")) throw new Error("offline");
      return defaultRead(path, options);
    });
    render(await page({ tab: "late" }));
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.queryByText("Nothing matches these filters.")).toBeNull();
  });
});
