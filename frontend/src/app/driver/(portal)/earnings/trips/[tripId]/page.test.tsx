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
