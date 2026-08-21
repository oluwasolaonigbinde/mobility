import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import AdminFraudPage from "./page";

const FLAG_ID = "00000000-0000-4000-8000-00000000000a";
const DISPUTE_ID = "00000000-0000-4000-8000-00000000000b";

describe("AdminFraudPage disputes", () => {
  beforeEach(() => get.mockReset());

  it("loads disputes for the visible flags and keeps the driver reply separate", async () => {
    get.mockImplementation(async () => {
      if (get.mock.calls.length === 1) {
        return {
          data: {
            items: [
              {
                id: FLAG_ID,
                trip_analytics_id: null,
                trip_session_id: "00000000-0000-4000-8000-000000000001",
                assignment_id: "00000000-0000-4000-8000-000000000002",
                campaign_id: "00000000-0000-4000-8000-000000000003",
                driver_profile_id: "00000000-0000-4000-8000-000000000004",
                vehicle_id: "00000000-0000-4000-8000-000000000005",
                flag_type: "route_replay",
                severity: "high",
                description: "Route resembles an earlier trip.",
                evidence: { fingerprint: "admin-only-evidence" },
                status: "acknowledged",
                detected_at: "2026-08-21T09:00:00Z",
                review_due_at: "2026-08-30T09:00:00Z",
                escalated_at: "2026-08-30T09:00:00Z",
                money_effect: {
                  available_net: "125.50",
                  currency: "NGN",
                  reversal_entry_id: null,
                  reversal_recommended: true,
                },
                reviewed_at: null,
                reviewed_by_user_id: null,
                resolution_note: null,
                created_at: "2026-08-21T09:00:00Z",
                updated_at: "2026-08-21T09:00:00Z",
              },
            ],
            total: 1,
            limit: 25,
            offset: 0,
          },
        };
      }
      return {
        data: {
          items: [
            {
              id: DISPUTE_ID,
              fraud_flag_id: FLAG_ID,
              driver_profile_id: "00000000-0000-4000-8000-000000000004",
              submitted_by_user_id: "00000000-0000-4000-8000-000000000006",
              message: "My phone lost signal near the bridge.",
              status: "open",
              reply: null,
              replied_at: null,
              replied_by_user_id: null,
              created_at: "2026-08-21T09:30:00Z",
              updated_at: "2026-08-21T09:30:00Z",
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        },
      };
    });

    render(await AdminFraudPage({ searchParams: Promise.resolve({}) }));

    const section = screen.getByRole("region", { name: "Driver dispute" });
    expect(within(section).getByText("My phone lost signal near the bridge.")).toBeInTheDocument();
    expect(within(section).getByLabelText("Reply to driver")).toBeInTheDocument();
    expect(screen.getByLabelText("Review note")).toBeInTheDocument();
    expect(screen.getByText("Review deadline passed")).toBeInTheDocument();
    expect(screen.getByText(/This review is unresolved/)).toBeInTheDocument();
    expect(screen.getByText(/30 Aug 2026/)).toBeInTheDocument();
    expect(screen.getByText(/₦125\.50/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirm fraud & reverse released earnings" }),
    ).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenNthCalledWith(1, "/api/v1/admin/fraud-flags", {
      params: { query: { limit: 25, offset: 0 } },
    });
    expect(get).toHaveBeenNthCalledWith(2, "/api/v1/admin/fraud-disputes", {
      params: { query: { flag_id: [FLAG_ID], limit: 25, offset: 0 } },
    });
  });

  it("does not request disputes when the visible page has no flags", async () => {
    get.mockResolvedValue({ data: { items: [], total: 0, limit: 25, offset: 0 } });

    render(await AdminFraudPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText(/No flags/)).toBeInTheDocument();
    expect(get).toHaveBeenCalledOnce();
  });

  it("describes a terminal escalation as historical, not unresolved", async () => {
    get
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: FLAG_ID,
              trip_analytics_id: null,
              trip_session_id: "00000000-0000-4000-8000-000000000001",
              assignment_id: "00000000-0000-4000-8000-000000000002",
              campaign_id: "00000000-0000-4000-8000-000000000003",
              driver_profile_id: "00000000-0000-4000-8000-000000000004",
              vehicle_id: "00000000-0000-4000-8000-000000000005",
              flag_type: "route_replay",
              severity: "high",
              description: "Route resembles an earlier trip.",
              evidence: {},
              status: "confirmed",
              detected_at: "2026-08-21T09:00:00Z",
              review_due_at: "2026-08-30T09:00:00Z",
              escalated_at: "2026-08-30T09:00:00Z",
              money_effect: {
                available_net: "0",
                currency: "NGN",
                reversal_entry_id: "00000000-0000-4000-8000-00000000000c",
                reversal_recommended: false,
              },
              reviewed_at: "2026-08-31T09:00:00Z",
              reviewed_by_user_id: "00000000-0000-4000-8000-000000000006",
              resolution_note: "Evidence confirmed.",
              created_at: "2026-08-21T09:00:00Z",
              updated_at: "2026-08-31T09:00:00Z",
            },
          ],
          total: 1,
          limit: 25,
          offset: 0,
        },
      })
      .mockResolvedValueOnce({ data: { items: [], total: 0, limit: 25, offset: 0 } });

    render(await AdminFraudPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("SLA exceeded before resolution")).toBeInTheDocument();
    expect(screen.queryByText(/This review is unresolved/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/released earnings were reversed/i)).toHaveLength(2);
  });
});
