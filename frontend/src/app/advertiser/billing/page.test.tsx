import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import AdvertiserBillingPage from "./page";

const receipt = (id: string, reference: string) => ({
  id,
  external_transaction_id: reference,
  payer_name: "Demo Advertiser",
  observed_at: "2026-09-01T10:00:00Z",
  amount: "250000.00",
  currency: "NGN",
});

describe("AdvertiserBillingPage", () => {
  beforeEach(() => get.mockReset());

  it("describes recorded payments in plain language without changing amounts or production meaning", async () => {
    get.mockImplementation(async (path?: string) => {
      if (path === "/api/v1/advertiser/billing") {
        return {
          data: [
            {
              receipt: receipt("r1", "TRF-001"),
              current_status: null,
              allocations: [],
              events: [],
            },
            {
              receipt: receipt("r2", "TRF-002"),
              current_status: "reconciled",
              allocations: [],
              events: [],
            },
            {
              receipt: receipt("r3", "TRF-003"),
              current_status: "confirmed",
              allocations: [{ id: "a1" }, { id: "a2" }],
              events: [],
            },
            {
              receipt: receipt("r4", "TRF-004"),
              current_status: "reversed",
              allocations: [{ id: "a3" }],
              events: [],
            },
          ],
        };
      }
      return { data: { items: [], total: 0 } };
    });

    render(await AdvertiserBillingPage());

    expect(
      screen.getByText("Payments recorded for your campaigns and how they were applied"),
    ).toBeInTheDocument();
    expect(screen.getByText("Recorded – being checked")).toBeInTheDocument();
    expect(screen.getByText("Amount matched – awaiting confirmation")).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getByText("Reversed")).toBeInTheDocument();
    expect(
      screen.getByText("Applied to your accepted campaign terms (2 allocations)"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Not yet applied – production cannot start from this payment."),
    ).toHaveLength(2);
    expect(
      screen.getByText("Reversed – this payment no longer counts toward your campaign terms."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("₦250,000")).toHaveLength(4);
    expect(
      screen.getByText("Online payment isn't available yet. Please pay by bank transfer."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/canonical|immutable|provider/i)).not.toBeInTheDocument();
  });

  it("shows a plain empty state when no payments exist", async () => {
    get.mockImplementation(async (path?: string) =>
      path === "/api/v1/advertiser/billing" ? { data: [] } : { data: { items: [], total: 0 } },
    );

    render(await AdvertiserBillingPage());

    expect(screen.getByText("No payments have been recorded yet.")).toBeInTheDocument();
  });
});
