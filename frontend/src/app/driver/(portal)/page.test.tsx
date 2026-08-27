import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
const loadJourney = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: vi.fn(async () => ({ user: { full_name: "Ada Driver" } })),
}));
vi.mock("@/lib/driver/load-campaign-journey", () => ({
  loadDriverCampaignJourney: loadJourney,
}));

import DriverHomePage from "./page";

const ledgerEntry = (status: "paid" | "pending", id: string) => ({
  id,
  amount: "1250.00",
  campaign_id: "00000000-0000-4000-8000-000000000001",
  created_at: "2026-08-23T09:00:00Z",
  currency: "NGN",
  description: null,
  driver_profile_id: "00000000-0000-4000-8000-000000000002",
  entry_type: "trip_payout" as const,
  occurred_at: "2026-08-23T09:00:00Z",
  payout_calculation_id: "00000000-0000-4000-8000-000000000003",
  status,
  trip_session_id: "00000000-0000-4000-8000-000000000004",
  vehicle_id: "00000000-0000-4000-8000-000000000005",
});

describe("DriverHomePage ledger statuses", () => {
  beforeEach(() => {
    get.mockReset();
    loadJourney.mockResolvedValue({
      journey: {
        standing: "PENDING",
        summary: "Campaign work remains pending.",
        canStart: false,
        hasCurrentTrip: false,
        steps: [],
      },
      activationAssignment: null,
      currentTrip: null,
      trackerAssignment: null,
    });
  });

  it("renders paid entries green and pending entries amber", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) return { data: { totals_by_currency: [] } };
      if (path?.endsWith("/active")) return { data: { assignment: null } };
      if (path?.endsWith("/current")) return { data: { trip: null } };
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return {
        data: {
          items: [
            ledgerEntry("paid", "00000000-0000-4000-8000-000000000010"),
            ledgerEntry("pending", "00000000-0000-4000-8000-000000000011"),
          ],
        },
      };
    });

    render(await DriverHomePage());

    expect(screen.getByText("paid")).toHaveClass("text-green");
    expect(screen.getByText("pending")).toHaveClass("text-amber");
  });

  it("shows debt-aware batch-payable earnings without hiding carried debt", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              {
                currency: "NGN",
                batch_payable_amount: "90.00",
                carry_forward_debt_amount: "60.00",
                lifetime_earned_amount: "190.00",
                pending_amount: "0.00",
              },
            ],
          },
        };
      }
      if (path?.endsWith("/active")) return { data: { assignment: null } };
      if (path?.endsWith("/current")) return { data: { trip: null } };
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return { data: { items: [] } };
    });

    render(await DriverHomePage());

    expect(screen.getByText("Batch-payable earnings")).toBeInTheDocument();
    expect(screen.getByText(/₦90\.00/)).toBeInTheDocument();
    expect(screen.getByText(/₦60\.00 carried debt/)).toBeInTheDocument();
  });

  it("does not claim the driver is ready when no server authority exists", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) return { data: { totals_by_currency: [] } };
      if (path?.endsWith("/active")) return { data: { assignment: null } };
      if (path?.endsWith("/current")) return { data: { trip: null } };
      return { data: { items: [], total: 0, limit: 50, offset: 0 } };
    });

    render(await DriverHomePage());

    expect(screen.queryByText("READY")).not.toBeInTheDocument();
    expect(screen.queryByText("vehicle active")).not.toBeInTheDocument();
  });
});
