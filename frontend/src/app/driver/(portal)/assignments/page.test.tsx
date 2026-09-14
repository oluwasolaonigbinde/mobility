import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn(), loadJourney: vi.fn() }));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/driver/load-campaign-journey", () => ({
  loadDriverCampaignJourney: mocks.loadJourney,
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
      screen.getByText("Accepted. Cardvert operations still need to activate this campaign."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Activated. Cardvert checks you're still ready each time you press Start."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/authority|PWA|independent admin/i)).not.toBeInTheDocument();
  });
});
