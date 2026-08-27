import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
const loadJourney = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/driver/load-campaign-journey", () => ({
  loadDriverCampaignJourney: loadJourney,
}));
vi.mock("./profile-form", () => ({ ProfileForm: () => <div>Profile form</div> }));

import DriverProfilePage from "./page";

describe("DriverProfilePage campaign authority", () => {
  beforeEach(() => {
    get.mockReset();
    loadJourney.mockResolvedValue({
      journey: {
        standing: "DEGRADED",
        summary: "Some authority could not be verified. Cardvert will not claim readiness.",
        canStart: false,
        hasCurrentTrip: false,
        steps: [
          {
            id: "vehicle",
            label: "Vehicle review",
            state: "degraded",
            title: "Vehicle status unavailable",
            detail: "Cardvert cannot verify current vehicle evidence.",
            href: "/driver/profile",
          },
        ],
      },
      activationAssignment: null,
      currentTrip: null,
      trackerAssignment: null,
    });
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/profile")) {
        return {
          data: {
            full_name: "Ada Driver",
            email: "ada@example.com",
            onboarding_status: "active",
          },
        };
      }
      if (path.endsWith("/vehicles")) {
        return {
          data: {
            items: [
              {
                id: "11111111-1111-4111-8111-111111111111",
                plate_number: "ABC-123",
                vehicle_type: "car",
                status: "active",
              },
            ],
          },
        };
      }
      if (path.endsWith("/campaign-assignments")) {
        return {
          data: {
            items: [
              {
                id: "22222222-2222-4222-8222-222222222222",
                status: "active",
              },
            ],
          },
        };
      }
      return { data: { items: [] } };
    });
  });

  it("does not publish a second readiness claim when canonical evidence is degraded", async () => {
    render(await DriverProfilePage());

    expect(screen.getByText("DEGRADED")).toBeInTheDocument();
    expect(screen.getByText("Vehicle status unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Ready to track and earn")).not.toBeInTheDocument();
    expect(screen.queryByText("Driver readiness")).not.toBeInTheDocument();
  });
});
