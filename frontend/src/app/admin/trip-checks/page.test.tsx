import { cleanup, render, screen, within } from "@testing-library/react";
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
  SpotCheckForm: () => <button>Record check</button>,
}));
vi.mock("../operation-form", () => ({ OperationForm: () => <button>Add to trip</button> }));
import TripChecks from "./page";
const date = "2026-09-03T07:15:00Z";
const flag = {
  id: "flag",
  flag_type: "impossible_speed",
  driver_name: "Ada Driver",
  vehicle_plate: "ABJ-101",
  campaign_name: "PalmPay Wuse",
  trip_started_at: date,
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
  driver_profile_id: "driver",
  campaign_id: "campaign",
  assignment_id: "job",
  driver_name: "Ada Driver",
  vehicle_plate: "ABJ-101",
  campaign_name: "PalmPay Wuse",
  trip_started_at: date,
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
  it("marks the default list and status as selected and shows only that list's statuses", async () => {
    render(await page());
    const lists = screen.getByRole("navigation", { name: "Trip check lists" });
    expect(within(lists).getByRole("link", { current: "page" })).toHaveTextContent(
      "Suspicious trips",
    );
    const statuses = screen.getByRole("navigation", { name: "Status" });
    expect(within(statuses).getByRole("link", { current: "page" })).toHaveTextContent("All");
    expect(within(statuses).queryByRole("link", { name: /Quarantined/i })).toBeNull();
    cleanup();
    render(await page({ tab: "late" }));
    const lateStatuses = screen.getByRole("navigation", { name: "Status" });
    expect(within(lateStatuses).getAllByRole("link")).toHaveLength(3);
    expect(within(lateStatuses).getByRole("link", { current: "page" })).toHaveAttribute(
      "href",
      expect.stringContaining("status=quarantined"),
    );
    cleanup();
    render(await page({ tab: "in-person" }));
    expect(screen.queryByRole("navigation", { name: "Status" })).toBeNull();
  });
  it("leads each trip with the driver and reason and keeps IDs secondary", async () => {
    render(await page());
    const card = screen.getByRole("link", { name: /Ada Driver/ });
    expect(card.textContent!.indexOf("Ada Driver")).toBeLessThan(
      card.textContent!.indexOf("Speed higher than the review limit"),
    );
    expect(card.textContent!.trim().endsWith("Trip trip · Review flag")).toBe(true);
  });
  it("keeps an in-person check reason plain and its check ID secondary", async () => {
    const checked = {
      ...flag,
      flag_type: "physical_spot_check_failed",
      evidence: { verification_id: "check-reference", result: {}, gps_claim: "none" },
    };
    get.mockImplementation(async (path, options) =>
      path.endsWith("/fraud-flags")
        ? { data: { items: [checked], total: 1 } }
        : defaultRead(path, options),
    );

    render(await page());

    const reason = screen.getByText("An in-person check found a problem");
    expect(reason).not.toHaveTextContent(/Result|Gps|check-reference|\{\}/);
    expect(screen.getByText(/Trip trip .* Check check-reference/)).toHaveClass("text-faint");
  });

  it("lists trips with the same route for a route-match review", async () => {
    const replay = {
      ...flag,
      flag_type: "route_replay",
      evidence: { total_match_count: 1, sampled_matched_trip_ids: ["earlier"] },
    };
    get.mockImplementation(async (path, options) =>
      path.endsWith("/fraud-flags")
        ? { data: { items: [replay], total: 1 } }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag" }));
    const matches = screen.getByRole("region", { name: "Matching trips" });
    expect(within(matches).getByText("Ada Driver")).toBeVisible();
    expect(within(matches).getByText(/Trip earlier/)).toBeVisible();
    expect(screen.getByText("Same route as 1 other trip")).toBeVisible();
    expect(screen.getByText("The driver hasn't disputed this.")).toBeVisible();
  });
  it("opens the selected trip map and keeps list filters when closing", async () => {
    render(await page({ flag: "flag", driver_profile_id: "driver", offset: "25" }));
    expect(
      screen.getByRole("img", { name: /Route sketch of recorded trip locations/ }),
    ).toBeVisible();
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
        return {
          data: {
            items: disputes.slice(start, start + Number(options.params?.query?.limit)),
            total: 101,
          },
        };
      }
      return defaultRead(path, options);
    });
    render(await page({ flag: "flag", disputes_offset: "100" }));
    expect(screen.getByText(/this review is unresolved and pay stays held/)).toBeVisible();
    expect(screen.getByRole("list", { name: "Detection evidence" })).toBeVisible();
    expect(screen.getByText("Driver explanation 100")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reply to driver" })).toBeVisible();
  });
  it("allows another observation after an earlier inspection result", async () => {
    get.mockImplementation(async (path, options) =>
      path.endsWith("/evidence-verifications")
        ? {
            data: {
              items: [{ id: "existing", source_trip_session_id: "trip", status: "passed" }],
              total: 1,
            },
          }
        : defaultRead(path, options),
    );
    render(await page({ flag: "flag" }));
    expect(screen.getByText("Record an in-person check")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /In-person check waiting/ })).toBeNull();
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
    expect(screen.queryByText("Record an in-person check")).toBeNull();
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
  it("opens an inspection result beyond the first hundred", async () => {
    const rows = Array.from({ length: 101 }, (_, index) => ({
      id: `check-${index}`,
      source_trip_session_id: "trip",
      assignment_id: "job",
      driver_profile_id: "driver",
      campaign_id: "campaign",
      status: "passed",
      result_note: "All panels were secure during inspection.",
      verification_type: "physical_spot_check",
      issued_at: date,
      driver_name: "Ada Driver",
      vehicle_plate: "ABJ-101",
      campaign_name: "PalmPay Wuse",
      trip_started_at: date,
    }));
    get.mockImplementation(async (path, options) =>
      path.endsWith("/evidence-verifications")
        ? {
            data: {
              items: options.params.query.verification_id
                ? rows.filter((r) => r.id === options.params.query.verification_id)
                : rows.slice(
                    options.params.query.offset,
                    options.params.query.offset + options.params.query.limit,
                  ),
              total: 101,
            },
          }
        : defaultRead(path, options),
    );
    render(await page({ tab: "in-person", check: "check-100", offset: "100" }));
    expect(screen.getByText(/Passed · All panels were secure during inspection\./)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Record check" })).toBeNull();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/evidence-verifications", {
      params: {
        query: {
          limit: 25,
          offset: 100,
          verification_id: undefined,
          trip_session_id: undefined,
          driver_profile_id: undefined,
          campaign_id: undefined,
          verification_type: "physical_spot_check",
        },
      },
    });
  });
  it("loads list context without an analytics request", async () => {
    get.mockImplementation(async (path, options) => {
      if (path.endsWith("/analytics")) throw new Error("offline");
      return defaultRead(path, options);
    });
    render(await page({ tab: "late" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(get.mock.calls.some(([path]) => path.endsWith("/analytics"))).toBe(false);
  });
});
