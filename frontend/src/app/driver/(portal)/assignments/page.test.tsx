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

    render(await DriverAssignmentsPage());

    expect(screen.getByRole("alert")).toHaveTextContent(/campaign history is unavailable/i);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /couldn't load your current or completed jobs\. Try again shortly\./i,
    );
    expect(screen.queryByText("No jobs yet")).not.toBeInTheDocument();
  });

  function mockJobs(items: unknown[]) {
    mocks.get.mockImplementation(async (path?: string) => {
      if (path === "/api/v1/driver/campaign-assignments") return { data: { items } };
      if (path === "/api/v1/driver/installation-evidence/policy") {
        return { data: { configured: false, can_upload: false, required_views: [] } };
      }
      if (path === "/api/v1/driver/evidence-verifications/pending") return { data: { items: [] } };
      throw new Error(`Unexpected request: ${path}`);
    });
  }

  it("explains who assigns offers when there are no jobs", async () => {
    mockJobs([]);

    render(await DriverAssignmentsPage());

    expect(
      screen.getByText("Campaign offers appear here once our team assigns your vehicle."),
    ).toBeInTheDocument();
  });

  it("keeps the activation and Start checks in plain status explanations", async () => {
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

    render(await DriverAssignmentsPage());

    expect(
      screen.getByText("Accepted. Terrax Media still needs to start this campaign for you."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Activated. Cardvert checks you're still ready each time you press Start."),
    ).toBeInTheDocument();
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
          payout: { revision_id: "r-1", hourly_rate_naira: "1500.00" },
          zones: { target: [{ id: "z-1", name: "Wuse II", wkt: "MULTIPOLYGON EMPTY" }] },
        },
        campaign: { name: "Abuja offer" },
        vehicle: { plate_number: "ABC-125", vehicle_type: "sedan" },
      },
    ]);

    const { container } = render(await DriverAssignmentsPage());

    expect(screen.getByText("Full job terms")).toBeInTheDocument();
    expect(screen.getByText("Zones · Target")).toBeInTheDocument();
    expect(screen.getByText("Wuse II")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/f{64}|r-1|z-1|MULTIPOLYGON|Technical reference/);
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
            outside_area_weight: "1.0000",
          },
          eligibility: { stationary_window_seconds: 300, max_ping_gap_seconds: 120 },
        },
        campaign: { name: "Abuja daily" },
        vehicle: { plate_number: "ABC-125", vehicle_type: "sedan" },
      },
    ]);

    render(await DriverAssignmentsPage());

    expect(screen.getByText("₦10,000 for a full day of 70 miles.")).toBeInTheDocument();
    expect(
      screen.getByText("Shorter days are paid in proportion to the miles covered."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\/hr/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Daily cap/)).not.toBeInTheDocument();
  });
});
