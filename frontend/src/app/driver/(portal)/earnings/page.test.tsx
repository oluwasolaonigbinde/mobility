import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ refresh: vi.fn() }),
}));

import DriverEarningsPage from "./page";

function earningsTotal(overrides: Record<string, string | number | null> = {}) {
  return {
    available_amount: "0.00",
    batch_payable_amount: "0.00",
    carry_forward_debt_amount: "0.00",
    cash_paid_amount: "0.00",
    currency: "NGN",
    ledger_entry_count: 0,
    lifetime_earned_amount: "0.00",
    paid_amount: "0.00",
    pending_amount: "0.00",
    released_available_amount: "0.00",
    voided_amount: "0.00",
    ...overrides,
  };
}

function ledgerPage(items: unknown[], total = items.length, offset = 0) {
  return { items, total, limit: 50, offset };
}

describe("DriverEarningsPage canonical settlement projection", () => {
  beforeEach(() => get.mockReset());

  it("renders batch-payable and carried debt as distinct values", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              earningsTotal({
                batch_payable_amount: "90.00",
                carry_forward_debt_amount: "60.00",
                lifetime_earned_amount: "190.00",
              }),
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return { data: ledgerPage([]) };
    });

    render(await DriverEarningsPage({}));

    expect(screen.getByText("Available for payment")).toBeInTheDocument();
    expect(screen.getByText("Owed, taken from your payouts")).toBeInTheDocument();
    expect(screen.getAllByText("₦90.00")).toHaveLength(1);
    expect(screen.getAllByText("₦60.00")).toHaveLength(1);
  });

  it("does not claim a larger debt was already covered by available earnings", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              earningsTotal({
                batch_payable_amount: "0.00",
                carry_forward_debt_amount: "60.00",
                released_available_amount: "50.00",
                lifetime_earned_amount: "190.00",
              }),
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      return { data: ledgerPage([]) };
    });

    render(await DriverEarningsPage({}));

    expect(screen.getByText("Available for payment").nextElementSibling).toHaveTextContent("₦0.00");
    expect(screen.getByText("Owed, taken from your payouts").nextElementSibling).toHaveTextContent(
      "₦60.00",
    );
    expect(screen.queryByText(/already subtracted/i)).not.toBeInTheDocument();
  });

  it("renders every backend summary independently and distinguishes held from cleared pending rows", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              earningsTotal({
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
              }),
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
        data: ledgerPage([
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
        ]),
      };
    });

    render(await DriverEarningsPage({}));

    for (const label of ["Released", "Paid ledger", "Voided", "Owed, taken from your payouts"]) {
      expect(screen.getAllByText(label, { exact: true }).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("Held", { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText("Pending", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Adjustment", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Paid", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("Debt carried", { exact: true })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Ledger · earnings, corrections and debt" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/every naira traced to a trip/i)).not.toBeInTheDocument();
  });

  it("does not present an empty or cached balance when any canonical source is unavailable", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) return {};
      return { data: { items: [] } };
    });

    render(await DriverEarningsPage({}));

    expect(screen.getByRole("alert")).toHaveTextContent(
      /earnings and review status are unavailable/i,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /couldn't load your latest earnings, ledger or trip reviews, so no balance is shown\. Try again shortly\./i,
    );
    expect(screen.queryByText(/No entries yet/)).not.toBeInTheDocument();
    expect(screen.queryByText(/₦/)).not.toBeInTheDocument();
  });

  it("keeps authoritative money visible when only optional campaign labels fail", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              earningsTotal({
                batch_payable_amount: "90.00",
                cash_paid_amount: "40.00",
                pending_amount: "20.00",
              }),
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) {
        throw new ApiError(503, {
          code: "PROVIDER_UNAVAILABLE",
          message: "private upstream detail",
        });
      }
      if (path?.endsWith("/fraud-holds")) return { data: { items: [] } };
      return { data: ledgerPage([]) };
    });

    render(await DriverEarningsPage({}));

    expect(screen.getByText("Campaign labels unavailable")).toBeInTheDocument();
    expect(screen.getByText("Available for payment").nextElementSibling).toHaveTextContent(
      "₦90.00",
    );
    expect(screen.getByText("Under review").nextElementSibling).toHaveTextContent(
      "0 active trip holds",
    );
    expect(screen.getByText(/Pending ledger total/)).toHaveTextContent("₦20.00");
    expect(screen.getByText("Paid", { exact: true }).nextElementSibling).toHaveTextContent(
      "₦40.00",
    );
    expect(screen.queryByText("private upstream detail")).not.toBeInTheDocument();
  });

  it("uses backend pagination facts and keeps the payment hierarchy truthful beyond 50 rows", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return {
          data: {
            totals_by_currency: [
              earningsTotal({
                available_amount: "100.00",
                batch_payable_amount: "90.00",
                carry_forward_debt_amount: "10.00",
                cash_paid_amount: "40.00",
                ledger_entry_count: 75,
                lifetime_earned_amount: "150.00",
                paid_amount: "40.00",
                pending_amount: "20.00",
                released_available_amount: "100.00",
                voided_amount: "0.00",
              }),
            ],
          },
        };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      if (path?.endsWith("/fraud-holds")) return { data: { items: [] } };
      const items = Array.from({ length: 50 }, (_, index) => ({
        id: `entry-${index}`,
        campaign_id: "campaign-1",
        trip_session_id: null,
        entry_type: "adjustment",
        status: "available",
        amount: "1.00",
        currency: "NGN",
        description: `Entry ${index + 1}`,
        occurred_at: "2026-08-27T09:00:00Z",
      }));
      return { data: ledgerPage(items, 75) };
    });

    render(await DriverEarningsPage({ searchParams: Promise.resolve({}) }));

    expect(get).toHaveBeenCalledWith("/api/v1/driver/earnings/ledger", {
      params: { query: { limit: 50, offset: 0 } },
    });
    expect(screen.getByText("Available for payment")).toBeInTheDocument();
    expect(screen.getByText("Under review")).toBeInTheDocument();
    expect(screen.getByText("Paid", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Showing 1–50 of 75 entries")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/driver/earnings?offset=50",
    );
  });

  it("renders the authoritative second page with truthful row numbers", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return { data: { totals_by_currency: [earningsTotal({ ledger_entry_count: 75 })] } };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      if (path?.endsWith("/fraud-holds")) return { data: { items: [] } };
      const items = Array.from({ length: 25 }, (_, index) => ({
        id: `entry-${index + 50}`,
        campaign_id: "campaign-1",
        trip_session_id: null,
        entry_type: "adjustment",
        status: "available",
        amount: "1.00",
        currency: "NGN",
        description: `Entry ${index + 51}`,
        occurred_at: "2026-08-27T09:00:00Z",
      }));
      return { data: ledgerPage(items, 75, 50) };
    });

    render(await DriverEarningsPage({ searchParams: Promise.resolve({ offset: "50" }) }));

    expect(get).toHaveBeenCalledWith("/api/v1/driver/earnings/ledger", {
      params: { query: { limit: 50, offset: 50 } },
    });
    expect(screen.getByText("Showing 51–75 of 75 entries")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/driver/earnings?offset=0",
    );
    expect(screen.queryByRole("link", { name: "Next" })).not.toBeInTheDocument();
  });

  it("renders a truthful recovery path when the requested offset is past the end", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path?.endsWith("/summary")) {
        return { data: { totals_by_currency: [earningsTotal({ ledger_entry_count: 75 })] } };
      }
      if (path?.endsWith("/campaign-assignments")) return { data: { items: [] } };
      if (path?.endsWith("/fraud-holds")) return { data: { items: [] } };
      return { data: ledgerPage([], 75, 500) };
    });

    render(await DriverEarningsPage({ searchParams: Promise.resolve({ offset: "500" }) }));

    expect(screen.getByText("No entries at this position · 75 total")).toBeInTheDocument();
    expect(screen.queryByText("Showing 0–500 of 75 entries")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to the last page" })).toHaveAttribute(
      "href",
      "/driver/earnings?offset=50",
    );
  });
});
