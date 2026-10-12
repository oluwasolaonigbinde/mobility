import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ earnings: vi.fn(), journey: vi.fn(), tracker: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({}) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({ user: { id: "driver", full_name: "Ada Driver" } }),
}));
vi.mock("@/lib/driver/load-daily-earnings", () => ({ loadDailyEarnings: mocks.earnings }));
vi.mock("@/lib/driver/load-campaign-journey", () => ({ loadDriverCampaignJourney: mocks.journey }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
}));

vi.mock("./trip-tracker", () => ({
  TripTracker: (props: unknown) => {
    mocks.tracker(props);
    return <div>Trip tracker</div>;
  },
}));
import Track from "./page";
it("keeps only the tracker and passes current authority for recovery", async () => {
  const assignment = { id: "job", campaignName: "Abuja launch" };
  const trip = { id: "trip" };
  mocks.journey.mockResolvedValue({
    journey: { steps: [], canStart: false },
    trackerAssignment: null,
    activationAssignment: assignment,
    currentTrip: trip,
  });
  render(await Track());
  expect(mocks.tracker).toHaveBeenCalledWith(
    expect.objectContaining({ initialTrip: trip, assignment: null, driverId: "driver" }),
  );
  expect(screen.getByText("Trip tracker")).toBeVisible();
  expect(
    screen.queryByText(/How a trip|Recent verified|Set up this phone/),
  ).not.toBeInTheDocument();
});
