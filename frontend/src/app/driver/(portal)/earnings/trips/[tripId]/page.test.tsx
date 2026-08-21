import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/lib/api/schema";

const get = vi.fn();

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ GET: get }),
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: vi.fn() }));

import DriverTripEarningsPage from "./page";

type Breakdown = components["schemas"]["DriverTripEarningsBreakdown"];

function breakdown(overrides: Partial<Breakdown> = {}): Breakdown {
  return {
    trip_session_id: "00000000-0000-4000-8000-000000000001",
    formula_version: "payout_v3",
    amount: "750.00",
    currency: "NGN",
    hourly_rate: "1000.00",
    eligible_seconds: 2700,
    capped_seconds: 2700,
    excluded_seconds_by_reason: {},
    cap: null,
    entries: [],
    superseded_by_recompute: false,
    base_payable_seconds: 1800,
    premium_payable_seconds: 900,
    base_hourly_rate: "1000.00",
    premium_hourly_rate: "2000.00",
    base_amount: "500.00",
    premium_amount: "250.00",
    ...overrides,
  };
}

describe("DriverTripEarningsPage", () => {
  beforeEach(() => get.mockReset());

  it("labels payout_v3 and explains its frozen base and premium components", async () => {
    get.mockResolvedValue({ data: breakdown() });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-1" }) }));

    expect(screen.getByText(/Payout v3 · frozen base\/premium terms/)).toBeInTheDocument();
    const panel = screen.getByRole("heading", { name: "Frozen tier breakdown" }).parentElement;
    if (!panel) throw new Error("expected tier breakdown panel");
    expect(within(panel).getByText("Base tier")).toBeInTheDocument();
    expect(within(panel).getByText("Premium tier")).toBeInTheDocument();
    expect(within(panel).getByText(/30m.*1,000\.00\/hour/)).toBeInTheDocument();
    expect(within(panel).getByText(/15m.*2,000\.00\/hour/)).toBeInTheDocument();
    expect(within(panel).getByText(/500\.00/)).toBeInTheDocument();
    expect(within(panel).getByText(/250\.00/)).toBeInTheDocument();
  });

  it("preserves the payout_v2 hourly explanation without a tier panel", async () => {
    get.mockResolvedValue({
      data: breakdown({
        formula_version: "payout_v2",
        base_payable_seconds: null,
        premium_payable_seconds: null,
        base_hourly_rate: null,
        premium_hourly_rate: null,
        base_amount: null,
        premium_amount: null,
      }),
    });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-2" }) }));

    expect(screen.getByText(/1,000\.00\/hour × 45m verified time/)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Frozen tier breakdown" }),
    ).not.toBeInTheDocument();
  });

  it("shows premium seconds at the disclosed base-rate fallback", async () => {
    get.mockResolvedValue({ data: breakdown({ premium_hourly_rate: null }) });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-3" }) }));

    const panel = screen.getByRole("heading", { name: "Frozen tier breakdown" }).parentElement;
    if (!panel) throw new Error("expected tier breakdown panel");
    expect(within(panel).getByText(/15m.*base rate.*1,000\.00\/hour/)).toBeInTheDocument();
  });

  it("explains rolling stationary exclusions in plain language", async () => {
    get.mockResolvedValue({
      data: breakdown({
        excluded_seconds_by_reason: { stationary_rolling_displacement: 360 },
      }),
    });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-4" }) }));

    expect(
      screen.getByText("Stationary after two 2-minute movement checks (shared grace applied)"),
    ).toBeInTheDocument();
    expect(screen.getByText("6m")).toBeInTheDocument();
  });
});
