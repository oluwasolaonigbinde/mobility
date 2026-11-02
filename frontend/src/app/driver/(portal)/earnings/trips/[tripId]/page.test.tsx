import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "@/lib/api/schema";
import { ApiError } from "@/lib/api/errors";

const { get, notFound, refresh } = vi.hoisted(() => ({
  get: vi.fn(),
  notFound: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ GET: get }),
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound, useRouter: () => ({ refresh }) }));

import DriverTripEarningsPage from "./page";

type Breakdown = components["schemas"]["DriverTripEarningsBreakdown"];

function breakdown(overrides: Partial<Breakdown> = {}): Breakdown {
  return {
    trip_session_id: "00000000-0000-4000-8000-000000000001",
    formula_version: "payout_v4",
    amount: "750.00",
    currency: "NGN",
    eligible_seconds: 2700,
    excluded_seconds_by_reason: {},
    entries: [],
    superseded_by_recompute: false,
    ...overrides,
  };
}

describe("DriverTripEarningsPage", () => {
  beforeEach(() => {
    get.mockReset();
    notFound.mockReset();
  });

  it("explains payout_v4 per-day miles and pay without internal codes", async () => {
    get.mockResolvedValue({
      data: breakdown({
        formula_version: "payout_v4",
        amount: "3500.00",
        excluded_seconds_by_reason: { stationary: 420 },
        daily_rate_days: [
          { lagos_day: "2026-07-20", distance_m: 48280, amount: "3000.00" },
          { lagos_day: "2026-07-21", distance_m: 8047, amount: "500.00" },
        ],
      }),
    });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-v4" }) }));

    expect(screen.queryByText(/day rate|proportional|time only counts/i)).not.toBeInTheDocument();
    const panel = screen.getByRole("heading", { name: "Miles counted" }).parentElement;
    if (!panel) throw new Error("expected miles panel");
    expect(within(panel).getByText(/^30\.0 miles counted on this trip/)).toBeInTheDocument();
    expect(within(panel).getByText(/^5\.0 miles counted on this trip/)).toBeInTheDocument();
    expect(within(panel).getByText(/3,000\.00/)).toBeInTheDocument();
    expect(within(panel).getByText(/500\.00/)).toBeInTheDocument();
    expect(within(panel).getByText("Stops longer than 5 minutes")).toBeInTheDocument();
    expect(screen.queryByText(/payout_v4|d39|stationary/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Verified time" })).not.toBeInTheDocument();
  });
  it("labels an overpayment correction as a deduction, not a release", async () => {
    const entry = {
      id: "00000000-0000-4000-8000-0000000000e1",
      currency: "NGN",
      description: "Correct overpayment",
      occurred_at: "2026-10-26T10:00:00Z",
    };
    get.mockResolvedValue({
      data: breakdown({
        entries: [
          { ...entry, entry_type: "reversal", status: "available", amount: "100.00" },
          {
            ...entry,
            id: "00000000-0000-4000-8000-0000000000e2",
            description: "Withdrawn correction",
            entry_type: "reversal",
            status: "voided",
            amount: "40.00",
          },
        ] as Breakdown["entries"],
      }),
    });

    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-v4" }) }));

    const deduction = screen.getAllByText("Deduction")[0]?.closest("li");
    if (!deduction) throw new Error("expected the correction entry");
    expect(within(deduction).getAllByText("Deduction")).toHaveLength(2);
    expect(within(deduction).queryByText("Released")).not.toBeInTheDocument();
    expect(screen.queryByText("Correct overpayment")).not.toBeInTheDocument();
    expect(screen.queryByText("Withdrawn correction")).not.toBeInTheDocument();
    const withdrawn = screen.getByText("Voided").closest("li");
    if (!withdrawn) throw new Error("expected the voided entry");
    expect(within(withdrawn).getAllByText("Deduction")).toHaveLength(1);
  });

  it.each(["Manual negative adjustment", "Day true-up reversal"])(
    "hides %s, keeps miles and dates the deduction by its work day",
    async (description) => {
      get.mockResolvedValue({
        data: breakdown({
          amount: "9900.00",
          to_deduct: "100.00",
          cash_paid: "10000.00",
          daily_rate_days: [{ lagos_day: "2026-10-24", distance_m: 119575, amount: "10000.00" }],
          entries: [
            {
              id: "00000000-0000-4000-8000-0000000000e3",
              currency: "NGN",
              description,
              entry_type: "reversal",
              status: "available",
              amount: "100.00",
              occurred_at: "2026-10-27T09:00:00Z",
              work_days: [{ day: "2026-10-24", amount: "100.00" }],
            },
          ] as Breakdown["entries"],
        }),
      });

      render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-v4" }) }));

      expect(screen.getByText("₦9,900.00")).toBeInTheDocument();
      expect(screen.getByText("₦10,000.00 paid · ₦100.00 to be deducted")).toBeInTheDocument();
      expect(screen.getByText(/^74\.3 miles counted on this trip/)).toBeInTheDocument();
      expect(screen.queryByText("No miles counted on this trip.")).not.toBeInTheDocument();
      expect(screen.queryByText(description)).not.toBeInTheDocument();
      const deduction = screen.getAllByText("Deduction")[0]?.closest("li");
      if (!deduction) throw new Error("expected the deduction entry");
      expect(within(deduction).getAllByText("Deduction")).toHaveLength(2);
      expect(within(deduction).getByText(/24 Oct/)).toBeInTheDocument();
      expect(within(deduction).queryByText(/27 Oct/)).not.toBeInTheDocument();
    },
  );

  it("explains partial recovery using the existing amounts", async () => {
    get.mockResolvedValue({
      data: breakdown({ amount: "9700.00", cash_paid: "10000.00", to_deduct: "208.92" }),
    });
    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-v4" }) }));
    expect(screen.getByText(/₦91.08 already deducted/)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Entries for this trip" }),
    ).not.toBeInTheDocument();
  });
  it("shows no deduction note once nothing is left to deduct", async () => {
    get.mockResolvedValue({ data: breakdown({ amount: "9900.00", to_deduct: "0.00" }) });
    render(await DriverTripEarningsPage({ params: Promise.resolve({ tripId: "trip-v4" }) }));
    expect(screen.queryByText(/to be deducted/)).not.toBeInTheDocument();
  });

  it("renders only public hold, notice and dispute fields", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.includes("earnings-breakdown")) return { data: breakdown() };
      return {
        data: {
          items: [
            {
              id: "00000000-0000-4000-8000-00000000000a",
              trip_session_id: "00000000-0000-4000-8000-000000000001",
              public_status: "under_review",
              reason: {
                code: "route_pattern_review",
                title: "Route pattern needs review",
                body: "We are checking an unusual route pattern before releasing these earnings.",
                version: "v1",
              },
              detected_at: "2026-08-21T09:00:00Z",
              reviewed_at: null,
              notices: [
                {
                  id: "00000000-0000-4000-8000-00000000000c",
                  type_key: "fraud_dispute_replied",
                  fraud_flag_id: "00000000-0000-4000-8000-00000000000a",
                  fraud_dispute_id: "00000000-0000-4000-8000-00000000000d",
                  trip_session_id: "00000000-0000-4000-8000-000000000001",
                  template_version: "v1",
                  outcome: "raw_internal_outcome",
                  created_at: "2026-08-21T10:00:00Z",
                },
              ],
              dispute: {
                id: "00000000-0000-4000-8000-00000000000d",
                message: "My signal dropped near the bridge.",
                status: "replied",
                submitted_at: "2026-08-21T09:30:00Z",
                reply: "We checked the route and completed the review.",
                replied_at: "2026-08-21T10:00:00Z",
              },
              evidence: "secret_route_hash",
              internal_note: "do_not_expose",
              matched_trip_id: "private_matched_trip",
            },
          ],
        },
      };
    });

    const { container } = render(
      await DriverTripEarningsPage({
        params: Promise.resolve({ tripId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );

    expect(screen.getByText("Route pattern needs review")).toBeInTheDocument();
    expect(screen.getByText("Under review")).toBeInTheDocument();
    expect(screen.getByText("Terrax Media replied to you.")).toBeInTheDocument();
    expect(screen.getByText("My signal dropped near the bridge.")).toBeInTheDocument();
    expect(screen.getByText("We checked the route and completed the review.")).toBeInTheDocument();
    expect(container).not.toHaveTextContent(/secret_route_hash|do_not_expose|private_matched_trip/);
    expect(container).not.toHaveTextContent("raw_internal_outcome");
  });

  it("does not request holds after a missing earnings breakdown", async () => {
    get.mockRejectedValue(new ApiError(404, { code: "NOT_FOUND", message: "Trip not found" }));
    notFound.mockImplementation(() => {
      throw new Error("NEXT_NOT_FOUND");
    });

    await expect(
      DriverTripEarningsPage({
        params: Promise.resolve({ tripId: "00000000-0000-4000-8000-000000000001" }),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
    expect(get).toHaveBeenCalledTimes(1);
    expect(notFound).toHaveBeenCalledOnce();
  });

  it("withholds a verified amount when current hold authority is unavailable", async () => {
    get
      .mockResolvedValueOnce({ data: breakdown() })
      .mockRejectedValueOnce(
        new ApiError(503, { code: "PROVIDER_UNAVAILABLE", message: "provider unavailable" }),
      );

    render(
      await DriverTripEarningsPage({
        params: Promise.resolve({ tripId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent(/trip review status is unavailable/i);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /couldn't check whether this trip is under review/i,
    );
    expect(screen.queryByText("₦750.00")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Dispute message")).not.toBeInTheDocument();
  });
});
