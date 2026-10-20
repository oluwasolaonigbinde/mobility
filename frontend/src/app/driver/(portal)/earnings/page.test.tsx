import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
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

import Earnings from "./page";
beforeEach(() => vi.clearAllMocks());
it("shows days with one status and details reachable", async () => {
  mocks.earnings.mockResolvedValue({
    state: "ready",
    data: {
      totals: [],
      days: [
        {
          day: "2026-10-09",
          amount: "10000.00",
          currency: "NGN",
          status: "Paid 10 Oct",
          tripIds: ["trip"],
        },
      ],
    },
  });
  render(await Earnings());
  expect(screen.getByText("₦10,000.00")).toBeVisible();
  expect(screen.getAllByText("Paid 10 Oct")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Trip 1", hidden: true })).toHaveAttribute(
    "href",
    "/driver/earnings/trips/trip",
  );
  expect(
    screen.queryByText(/Ready to be paid|How you get paid|Available/i),
  ).not.toBeInTheDocument();
});
it("links a held day to support", async () => {
  mocks.earnings.mockResolvedValue({
    state: "ready",
    data: {
      totals: [],
      days: [
        {
          day: "2026-10-09",
          amount: "100",
          currency: "NGN",
          status: "On hold – contact support",
          tripIds: [],
        },
      ],
    },
  });
  render(await Earnings());
  expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/driver/help");
});
it("shows this week, total and on-hold money from the server", async () => {
  mocks.earnings.mockResolvedValue({
    state: "ready",
    data: {
      totals: [
        {
          currency: "NGN",
          today: "0.00",
          this_week: "2500.00",
          total: "12500.00",
          on_hold: "100.00",
        },
      ],
      days: [
        {
          day: "2026-10-09",
          amount: "100.00",
          currency: "NGN",
          status: "On hold – contact support",
          tripIds: [],
        },
      ],
    },
  });
  render(await Earnings());
  expect(screen.getByText("This week").nextSibling).toHaveTextContent("₦2,500.00");
  expect(screen.getByText("Total").nextSibling).toHaveTextContent("₦12,500.00");
  expect(screen.getByText("On hold").nextSibling).toHaveTextContent("₦100.00");
});
it("shows successful empty history", async () => {
  mocks.earnings.mockResolvedValue({ state: "ready", data: { totals: [], days: [] } });
  render(await Earnings());
  expect(screen.getByText("No earnings yet.")).toBeVisible();
});
it("hides partial totals on failure", async () => {
  mocks.earnings.mockResolvedValue({ state: "unavailable" });
  render(await Earnings());
  expect(screen.getByRole("alert")).toHaveTextContent("complete daily history");
});
it("redirects expired sessions", async () => {
  mocks.earnings.mockResolvedValue({ state: "auth" });
  await expect(Earnings()).rejects.toThrow("redirect:/login");
});
