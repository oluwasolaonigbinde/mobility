import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import AdminAssignmentsPage from "./page";

const ASSIGNMENT_ID = "00000000-0000-4000-8000-00000000000a";

describe("AdminAssignmentsPage activity operations", () => {
  beforeEach(() => get.mockReset());

  it("renders current activity states and recovery evidence without trip evidence", async () => {
    get.mockResolvedValue({
      data: {
        items: [
          {
            id: ASSIGNMENT_ID,
            campaign_id: "00000000-0000-4000-8000-00000000000b",
            driver_profile_id: "00000000-0000-4000-8000-00000000000c",
            vehicle_id: "00000000-0000-4000-8000-00000000000d",
            assigned_by_user_id: "00000000-0000-4000-8000-00000000000e",
            status: "active",
            offered_at: "2026-08-24T09:00:00Z",
            expires_at: null,
            accepted_at: "2026-08-24T10:00:00Z",
            declined_at: null,
            expired_at: null,
            activated_at: "2026-08-24T10:00:00Z",
            deactivated_at: null,
            cancelled_at: null,
            completed_at: null,
            notes: null,
            metadata: {},
            offer_terms: null,
            offer_terms_sha256: null,
            created_at: "2026-08-24T09:00:00Z",
            updated_at: "2026-08-24T10:00:00Z",
            campaign: {
              id: "00000000-0000-4000-8000-00000000000b",
              name: "Rainy season launch",
              status: "active",
              start_at: null,
              end_at: null,
            },
            driver_profile: {
              id: "00000000-0000-4000-8000-00000000000c",
              user_id: "00000000-0000-4000-8000-00000000000f",
              onboarding_status: "active",
            },
            vehicle: {
              id: "00000000-0000-4000-8000-00000000000d",
              plate_number: "ACT-001",
              plate_country_code: "NG",
              vehicle_type: "car",
              status: "active",
            },
            events: [],
            activity_flags: [
              {
                id: "00000000-0000-4000-8000-000000000010",
                assignment_id: ASSIGNMENT_ID,
                campaign_id: "00000000-0000-4000-8000-00000000000b",
                driver_profile_id: "00000000-0000-4000-8000-00000000000c",
                vehicle_id: "00000000-0000-4000-8000-00000000000d",
                flag_type: "inactivity",
                status: "open",
                window_start: "2026-08-01T00:00:00Z",
                window_end: "2026-08-08T00:00:00Z",
                threshold_seconds: 604800,
                observed_seconds: 0,
                last_verified_activity_at: null,
                first_detected_at: "2026-08-08T00:00:00Z",
                last_evaluated_at: "2026-08-24T09:00:00Z",
                recovered_at: null,
                eligible_trip_count: 0,
                evidence_event_count: 1,
              },
              {
                id: "00000000-0000-4000-8000-000000000011",
                assignment_id: ASSIGNMENT_ID,
                campaign_id: "00000000-0000-4000-8000-00000000000b",
                driver_profile_id: "00000000-0000-4000-8000-00000000000c",
                vehicle_id: "00000000-0000-4000-8000-00000000000d",
                flag_type: "verified_hours_floor",
                status: "recovered",
                window_start: "2026-07-27T00:00:00Z",
                window_end: "2026-08-03T00:00:00Z",
                threshold_seconds: 3600,
                observed_seconds: 3600,
                last_verified_activity_at: "2026-08-02T12:00:00Z",
                first_detected_at: "2026-08-03T00:00:00Z",
                last_evaluated_at: "2026-08-24T09:00:00Z",
                recovered_at: "2026-08-24T09:00:00Z",
                eligible_trip_count: 1,
                evidence_event_count: 2,
              },
            ],
            total: 1,
            limit: 25,
            offset: 0,
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
      },
    });

    render(await AdminAssignmentsPage({ searchParams: Promise.resolve({}) }));

    const row = screen.getByText("Rainy season launch").closest("tr");
    if (!row) throw new Error("expected assignment row");
    expect(screen.getByRole("columnheader", { name: "Activity operations" })).toBeInTheDocument();
    expect(within(row).getByText("7-day inactivity open")).toBeInTheDocument();
    expect(within(row).getByText(/0s observed · 1 evidence event/)).toBeInTheDocument();
    expect(within(row).getByText("Weekly floor recovered")).toBeInTheDocument();
    expect(within(row).getByText(/3600s observed · 2 evidence events/)).toBeInTheDocument();
    expect(within(row).getByText(/Recovered/)).toBeInTheDocument();
    expect(screen.queryByText(/trip_session|analytics_source|secret/i)).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/campaign-assignments", {
      params: { query: { limit: 25, offset: 0 } },
    });
  });
});
