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
    expect(screen.queryByText("No jobs yet")).not.toBeInTheDocument();
  });
});
