import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import DriverEarningsPage from "./page";

describe("DriverEarningsPage canonical settlement projection", () => {
  beforeEach(() => get.mockReset());

  it("renders batch-payable and carried debt as distinct values", async () => {
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
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return { data: { items: [] } };
    });

    render(await DriverEarningsPage());

    expect(screen.getByText("Batch-payable")).toBeInTheDocument();
    expect(screen.getByText("Carried debt")).toBeInTheDocument();
    expect(screen.getAllByText("₦90.00")).toHaveLength(1);
    expect(screen.getAllByText("₦60.00")).toHaveLength(1);
  });

  it("renders every backend summary independently and distinguishes held from cleared pending rows", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              {
                currency: "NGN",
                available_amount: "80.00",
                batch_payable_amount: "70.00",
                carry_forward_debt_amount: "10.00",
                cash_paid_amount: "40.00",
                ledger_entry_count: 5,
                lifetime_earned_amount: "150.00",
                paid_amount: "40.00",
                pending_amount: "30.00",
                released_available_amount: "80.00",
                voided_amount: "5.00",
              },
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      if (path?.endsWith("/fraud-holds")) {
        return {
          data: {
            items: [
              {
                id: "00000000-0000-4000-8000-000000000011",
                trip_session_id: "00000000-0000-4000-8000-000000000001",
                public_status: "under_review",
              },
              {
                id: "00000000-0000-4000-8000-000000000012",
                trip_session_id: "00000000-0000-4000-8000-000000000002",
                public_status: "review_cleared",
              },
            ],
          },
        };
      }
      return {
        data: {
          items: [
            {
              id: "entry-held",
              campaign_id: "campaign-1",
              trip_session_id: "00000000-0000-4000-8000-000000000001",
              entry_type: "trip_payout",
              status: "pending",
              amount: "20.00",
              currency: "NGN",
              description: "Held trip",
              occurred_at: "2026-08-27T09:00:00Z",
            },
            {
              id: "entry-cleared",
              campaign_id: "campaign-1",
              trip_session_id: "00000000-0000-4000-8000-000000000002",
              entry_type: "trip_payout",
              status: "pending",
              amount: "10.00",
              currency: "NGN",
              description: "Cleared pending trip",
              occurred_at: "2026-08-27T10:00:00Z",
            },
            {
              id: "entry-released",
              campaign_id: "campaign-1",
              trip_session_id: "00000000-0000-4000-8000-000000000003",
              entry_type: "adjustment",
              status: "available",
              amount: "80.00",
              currency: "NGN",
              description: "Adjustment",
              occurred_at: "2026-08-27T11:00:00Z",
            },
            {
              id: "entry-paid",
              campaign_id: "campaign-1",
              trip_session_id: "00000000-0000-4000-8000-000000000004",
              entry_type: "trip_payout",
              status: "paid",
              amount: "40.00",
              currency: "NGN",
              description: "Paid trip",
              occurred_at: "2026-08-27T12:00:00Z",
            },
            {
              id: "entry-debt",
              campaign_id: "campaign-1",
              trip_session_id: null,
              entry_type: "debt_remainder",
              status: "reversed",
              amount: "10.00",
              currency: "NGN",
              description: "Debt remainder",
              occurred_at: "2026-08-27T13:00:00Z",
            },
          ],
        },
      };
    });

    render(await DriverEarningsPage());

    for (const label of ["Released", "Cash paid", "Voided", "Carried debt"]) {
      expect(screen.getAllByText(label, { exact: true }).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Held", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Pending", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Adjustment", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Paid", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("Debt carried", { exact: true })).toBeInTheDocument();
  });

  it("does not present an empty or cached balance when any canonical source is unavailable", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) return {};
      return { data: { items: [] } };
    });

    render(await DriverEarningsPage());

    expect(screen.getByRole("alert")).toHaveTextContent(
      /earnings and review status are unavailable/i,
    );
    expect(screen.queryByText(/No entries yet/)).not.toBeInTheDocument();
    expect(screen.queryByText(/₦/)).not.toBeInTheDocument();
  });
});
