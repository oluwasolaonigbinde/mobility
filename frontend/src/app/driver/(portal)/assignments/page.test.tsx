import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn(), loadJourney: vi.fn() }));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/driver/load-campaign-journey", () => ({
  loadDriverCampaignJourney: mocks.loadJourney,
}));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ refresh: vi.fn() }),
}));

import DriverAssignmentsPage from "./page";

describe("DriverAssignmentsPage history availability", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.loadJourney.mockResolvedValue({
      journey: { status: "not_ready", steps: [], canStart: false, hasCurrentTrip: false },
    });
  });

  it("shows unavailable rather than a successful empty history on provider failure", async () => {
    mocks.get.mockRejectedValue(
      new ApiError(503, { code: "PROVIDER_UNAVAILABLE", message: "provider unavailable" }),
    );

    render(await DriverAssignmentsPage({}));

    expect(screen.getByRole("alert")).toHaveTextContent(/campaign history is unavailable/i);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /couldn't load your current or completed jobs\. Try again shortly\./i,
    );
    expect(screen.queryByText("No jobs yet")).not.toBeInTheDocument();
  });

  function mockJobs(items: unknown[]) {
    mocks.get.mockImplementation(async (path?: string) => {
      if (path === "/api/v1/driver/campaign-assignments/active")
        return { data: { assignment: null, photo_status: "ready" } };
      if (path === "/api/v1/driver/campaign-assignments") return { data: { items } };
      if (path === "/api/v1/driver/installation-evidence/policy") {
        return {
          data: {
            required_views: ["front", "back", "left", "right", "close_up"],
            evidence_validity_hours: 168,
          },
        };
      }
      if (path === "/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence")
        return { data: { items: [] } };
      throw new Error(`Unexpected request: ${path}`);
    });
  }

  it("explains who assigns offers when there are no jobs", async () => {
    mockJobs([]);

    render(await DriverAssignmentsPage({}));

    expect(
      screen.getByText("Campaign offers appear here once our team assigns your vehicle."),
    ).toBeInTheDocument();
  });

  it("opens the exact owned job from a notification even beyond the first history page", async () => {
    mockJobs([]);
    const original = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation(async (path, options) =>
      path === "/api/v1/driver/campaign-assignments/{assignment_id}"
        ? {
            data: {
              id: "selected-job",
              campaign_id: "campaign",
              status: "completed",
              offered_at: "2026-09-01T09:00:00Z",
              offer_terms: null,
              campaign: { name: "Named selected campaign" },
              vehicle: { plate_number: "ABC-123", vehicle_type: "sedan" },
            },
          }
        : original(path, options),
    );
    render(
      await DriverAssignmentsPage({
        searchParams: Promise.resolve({ assignment_id: "selected-job" }),
      }),
    );
    expect(screen.getByText("Named selected campaign")).toBeInTheDocument();
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/driver/campaign-assignments/{assignment_id}", {
      params: { path: { assignment_id: "selected-job" } },
    });
    expect(mocks.get).not.toHaveBeenCalledWith(
      "/api/v1/driver/campaign-assignments",
      expect.anything(),
    );
  });

  it("shows unavailable when a notification's selected job cannot be read", async () => {
    mocks.get.mockResolvedValue({ error: { code: "ASSIGNMENT_NOT_FOUND" } });
    render(
      await DriverAssignmentsPage({
        searchParams: Promise.resolve({ assignment_id: "other-drivers-job" }),
      }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Campaign history is unavailable");
    expect(screen.queryByText("No jobs yet")).not.toBeInTheDocument();
  });

  it("shows a retry when current photo status cannot be checked", async () => {
    mockJobs([]);
    const normalRead = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/driver/campaign-assignments/active") {
        throw new ApiError(503, { code: "UNAVAILABLE", message: "Temporarily unavailable" });
      }
      return normalRead(path);
    });
    render(await DriverAssignmentsPage({}));
    expect(screen.getByText("Photo status is unavailable")).toBeVisible();
    expect(screen.getByRole("link", { name: /try again/i })).toHaveAttribute(
      "href",
      "/driver/assignments",
    );
    expect(screen.queryByText("No jobs yet")).not.toBeInTheDocument();
  });

  it("shows concise assignment states without operational explanations", async () => {
    mockJobs([
      {
        id: "00000000-0000-4000-8000-000000000010",
        campaign_id: "00000000-0000-4000-8000-000000000011",
        status: "accepted",
        offered_at: "2026-09-01T09:00:00Z",
        offer_terms: null,
        campaign: { name: "Abuja launch" },
        vehicle: { plate_number: "ABC-123", vehicle_type: "sedan" },
      },
      {
        id: "00000000-0000-4000-8000-000000000012",
        campaign_id: "00000000-0000-4000-8000-000000000013",
        status: "active",
        offered_at: "2026-09-01T09:00:00Z",
        offer_terms: null,
        campaign: { name: "Abuja live" },
        vehicle: { plate_number: "ABC-124", vehicle_type: "sedan" },
      },
    ]);

    render(await DriverAssignmentsPage({}));

    expect(screen.getByText("Accepted")).toBeVisible();
    expect(screen.getByText("Running")).toBeVisible();
    // The photo rule is built in (REQ-208): every current job can send its photos.
    expect(screen.getAllByText("Next, send 5 photos of the advert on your car.")).toHaveLength(2);
    expect(
      screen.queryByText(/can't be sent yet|Contact Terrax Media about the next step/),
    ).toBeNull();
    expect(screen.queryByText(/checks you're still ready/)).not.toBeInTheDocument();
    expect(screen.queryByText(/authority|PWA|independent admin/i)).not.toBeInTheDocument();
  });
  it("lists the accepted terms in words without the fingerprint or raw JSON (D38c)", async () => {
    mockJobs([
      {
        id: "00000000-0000-4000-8000-000000000014",
        campaign_id: "00000000-0000-4000-8000-000000000015",
        status: "offered",
        offered_at: "2026-09-01T09:00:00Z",
        offer_terms_sha256: "f".repeat(64),
        offer_terms: {
          currency: "NGN",
          payout: { revision_id: "r-1", formula_version: "payout_v4", daily_rate_naira: "1500.00" },
          zones: { target: [{ id: "z-1", name: "Wuse II", wkt: "MULTIPOLYGON EMPTY" }] },
        },
        campaign: { name: "Abuja offer" },
        vehicle: { plate_number: "ABC-125", vehicle_type: "sedan" },
      },
    ]);

    const { container } = render(await DriverAssignmentsPage({}));

    expect(screen.getByText("₦1,500.00 / day")).toBeVisible();
    expect(screen.queryByText("Full job terms")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/f{64}|r-1|z-1|MULTIPOLYGON|Technical reference/);
  });

  it("does not display an unset offered rate as zero", async () => {
    mockJobs([
      {
        id: "blank-rate-job",
        campaign_id: "blank-rate-campaign",
        status: "offered",
        offered_at: "2026-09-01T09:00:00Z",
        offer_terms: {
          currency: "NGN",
          payout: { formula_version: "payout_v4", daily_rate_naira: "" },
        },
        campaign: { name: "Rates not supplied" },
        vehicle: { plate_number: "ABC-126" },
      },
    ]);
    render(await DriverAssignmentsPage({}));
    expect(screen.getByText("Pay terms unavailable")).toBeInTheDocument();
    expect(screen.queryByText("₦0.00 / day")).not.toBeInTheDocument();
  });

  it.each([undefined, "unrecognized"])(
    "withholds pay for unsupported formula %s",
    async (formula) => {
      mockJobs([
        {
          id: "unknown-pay-job",
          campaign_id: "unknown-pay-campaign",
          status: "offered",
          offered_at: "2026-09-01T09:00:00Z",
          offer_terms: {
            currency: "NGN",
            payout: { formula_version: formula, daily_rate_naira: "1500.00" },
          },
          campaign: { name: "Unknown pay terms" },
          vehicle: { plate_number: "ABC-127" },
        },
      ]);
      render(await DriverAssignmentsPage({}));
      expect(screen.getByText("Pay terms unavailable")).toBeVisible();
      expect(screen.queryByText(/\/ hour|\/ day/)).not.toBeInTheDocument();
    },
  );

  it("dates past jobs by the driver's assignment instead of the campaign window", async () => {
    mockJobs([
      {
        id: "past-job",
        campaign_id: "campaign",
        status: "completed",
        offered_at: "2026-10-01T09:00:00Z",
        activated_at: "2026-10-02T09:00:00Z",
        completed_at: "2026-10-03T09:00:00Z",
        offer_terms: null,
        campaign: {
          name: "Finished early",
          start_at: "2026-10-01T09:00:00Z",
          end_at: "2026-12-01T09:00:00Z",
        },
        vehicle: { plate_number: "ABC-123" },
      },
    ]);

    const { container } = render(await DriverAssignmentsPage({}));

    expect(container.querySelector("summary")).toHaveTextContent("Finished 3 Oct 2026");
    expect(screen.queryByText("Finished", { exact: true })).not.toBeInTheDocument();
    expect(container.querySelector("summary")).not.toHaveTextContent("Dec 2026");
    expect(screen.getByText("Started 2 Oct 2026 – Finished 3 Oct 2026.")).toBeInTheDocument();
  });

  it("shows daily-rate pay terms as plain sentences instead of hourly lines", async () => {
    mockJobs([
      {
        id: "00000000-0000-4000-8000-000000000020",
        campaign_id: "00000000-0000-4000-8000-000000000021",
        status: "offered",
        offered_at: "2026-09-01T09:00:00Z",
        expires_at: "2026-10-01T09:00:00Z",
        offer_terms: {
          currency: "NGN",
          campaign_window_start_at: "2026-10-01T08:00:00+00:00",
          campaign_window_end_at: "2026-12-01T08:00:00+00:00",
          service_area: { city: "Abuja" },
          creative: { name: "Launch artwork" },
          zones: { target: [{ id: "z1", name: "Wuse II" }], exclusion: [] },
          payout: {
            formula_version: "payout_v4",
            daily_rate_naira: "10000.00",
            daily_target_miles: "70.000",
            shortfall_strategy: "proportional",
            deduction_per_mile_naira: null,
            minimum_miles: "0.000",
            outside_area_weight: "0.0000",
          },
          eligibility: { stationary_window_seconds: 300, max_ping_gap_seconds: 120 },
        },
        campaign: {
          name: "Abuja daily",
          start_at: "2027-01-01T08:00:00Z",
          end_at: "2027-02-01T08:00:00Z",
        },
        vehicle: { plate_number: "ABC-125", vehicle_type: "sedan" },
      },
    ]);

    render(await DriverAssignmentsPage({}));

    expect(
      screen.queryByText("₦10,000.00 a day for 70 miles; shorter days pay a share."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("₦10,000.00 / day")).toBeVisible();
    expect(screen.getByText("Wuse II")).toBeVisible();
    expect(screen.getByText(/1 Oct 2026.*1 Dec 2026/)).toBeVisible();
    expect(screen.queryByText(/1 Jan 2027|1 Feb 2027/)).toBeNull();
    expect(screen.queryByText(/Answer by|How pay works|full day of 70/)).not.toBeInTheDocument();
    expect(screen.queryByText("Currency: NGN")).not.toBeInTheDocument();
    expect(screen.queryByText(/target · \d+ exclusion/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("Shorter days are paid in proportion to the miles covered."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/\/hr/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Daily cap/)).not.toBeInTheDocument();
  });
});
