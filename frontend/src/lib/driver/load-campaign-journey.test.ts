import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "session-token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));

import { loadDriverCampaignJourney } from "./load-campaign-journey";

const ASSIGNMENT_ID = "22222222-2222-4222-8222-222222222222";
const VEHICLE_ID = "33333333-3333-4333-8333-333333333333";
const TRIP_ID = "11111111-1111-4111-8111-111111111111";

function installReadyResponses() {
  mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
    if (path === "/api/v1/driver/profile") {
      return { data: { onboarding_status: "active" } };
    }
    if (path === "/api/v1/driver/kyc/current") {
      return {
        data: {
          status: "approved",
          document_file_ids: { licence: "must-not-cross" },
          masked_nin: "*******1234",
        },
      };
    }
    if (path === "/api/v1/driver/vehicles") {
      return { data: { items: [{ id: VEHICLE_ID, status: "active" }], total: 1 } };
    }
    if (path === "/api/v1/driver/campaign-assignments/active") {
      return {
        data: {
          assignment: {
            id: ASSIGNMENT_ID,
            vehicle_id: VEHICLE_ID,
            campaign: { name: "Abuja Pilot" },
            vehicle: { plate_number: "ABC-123" },
            offer_terms: { sensitive: "must-not-cross" },
          },
        },
      };
    }
    if (path === "/api/v1/driver/trips/current") return { data: { trip: null } };
    if (path === "/api/v1/driver/campaign-assignments") {
      const query = (options as { params?: { query?: { status?: string } } })?.params?.query;
      return {
        data: { items: [], total: query?.status === "active" ? 1 : 0, limit: 1, offset: 0 },
      };
    }
    if (path === "/api/v1/driver/vehicles/{vehicle_id}") {
      return { data: { id: VEHICLE_ID, status: "active", plate_number: "ABC-123" } };
    }
    if (path === "/api/v1/driver/vehicles/{vehicle_id}/evidence-current") {
      return {
        data: {
          status: "approved",
          snapshot_trusted: true,
          document_file_ids: { insurance: "must-not-cross" },
        },
      };
    }
    throw new Error(`Unexpected path ${path}`);
  });
}

describe("loadDriverCampaignJourney", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    installReadyResponses();
  });

  it("projects canonical responses to a narrow status-only ready journey", async () => {
    const result = await loadDriverCampaignJourney();

    expect(result.journey.standing).toBe("READY");
    expect(result.trackerAssignment).toEqual({
      id: ASSIGNMENT_ID,
      campaignName: "Abuja Pilot",
      plateNumber: "ABC-123",
      vehicleId: VEHICLE_ID,
    });
    expect(JSON.stringify(result)).not.toMatch(
      /document_file_ids|masked_nin|offer_terms|must-not-cross/,
    );
  });

  it.each([401, 403])(
    "does not downgrade an auth failure (%s) into a degraded journey",
    async (status) => {
      mocks.get.mockImplementation(async (path: string) => {
        if (path === "/api/v1/driver/profile")
          throw new ApiError(status, { code: "AUTH", message: "session rejected" });
        return { data: undefined };
      });

      await expect(loadDriverCampaignJourney()).rejects.toMatchObject({ status });
    },
  );

  it.each([
    "/api/v1/driver/kyc/current",
    "/api/v1/driver/vehicles",
    "/api/v1/driver/campaign-assignments",
    "/api/v1/driver/campaign-assignments/active",
    "/api/v1/driver/trips/current",
    "/api/v1/driver/vehicles/{vehicle_id}",
    "/api/v1/driver/vehicles/{vehicle_id}/evidence-current",
  ])("preserves auth handling when %s rejects the session", async (failedPath) => {
    const ready = mocks.get.getMockImplementation();
    mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
      if (path === failedPath)
        throw new ApiError(403, { code: "FORBIDDEN", message: "session rejected" });
      return ready?.(path, options);
    });

    await expect(loadDriverCampaignJourney()).rejects.toMatchObject({ status: 403 });
  });

  it("treats active-assignment 404 as no canonical activation, not a missing profile", async () => {
    const ready = mocks.get.getMockImplementation();
    mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
      if (path === "/api/v1/driver/campaign-assignments/active")
        throw new ApiError(404, { code: "NOT_FOUND", message: "none" });
      if (path === "/api/v1/driver/campaign-assignments") {
        const status = (options as { params?: { query?: { status?: string } } })?.params?.query
          ?.status;
        return {
          data: {
            items: [],
            total: status === "accepted" ? 1 : 0,
            limit: 1,
            offset: 0,
          },
        };
      }
      return ready?.(path, options);
    });

    const result = await loadDriverCampaignJourney();

    expect(result.journey.standing).toBe("PENDING");
    expect(result.journey.steps.find((step) => step.id === "application")?.state).toBe("complete");
    expect(result.journey.steps.find((step) => step.id === "activation")?.title).toMatch(
      /waiting for admin/i,
    );
  });

  it("treats exact evidence 404 as not submitted and never as readiness", async () => {
    const ready = mocks.get.getMockImplementation();
    mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
      if (path === "/api/v1/driver/vehicles/{vehicle_id}/evidence-current")
        throw new ApiError(404, { code: "VEHICLE_EVIDENCE_NOT_FOUND", message: "none" });
      return ready?.(path, options);
    });

    const result = await loadDriverCampaignJourney();

    expect(result.journey.canStart).toBe(false);
    expect(result.journey.steps.find((step) => step.id === "vehicle")?.state).toBe("pending");
  });

  it.each(["/api/v1/driver/vehicles", "/api/v1/driver/campaign-assignments"])(
    "degrades instead of inventing absence when collection %s returns 404",
    async (failedPath) => {
      const ready = mocks.get.getMockImplementation();
      mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
        if (
          path === "/api/v1/driver/campaign-assignments/active" &&
          failedPath.endsWith("vehicles")
        ) {
          return { data: { assignment: null } };
        }
        if (path === "/api/v1/driver/profile" && failedPath.endsWith("campaign-assignments")) {
          throw new ApiError(404, { code: "PROFILE_NOT_FOUND", message: "none" });
        }
        if (path === failedPath) {
          throw new ApiError(404, { code: "ROUTE_NOT_FOUND", message: "unavailable" });
        }
        return ready?.(path, options);
      });

      const result = await loadDriverCampaignJourney();

      expect(result.journey.standing).toBe("DEGRADED");
      expect(
        result.journey.steps.find((step) =>
          failedPath.endsWith("vehicles") ? step.id === "vehicle" : step.id === "offer",
        )?.state,
      ).toBe("degraded");
      expect(result.trackerAssignment).toBeNull();
    },
  );

  it("degrades and withholds Start when exact vehicle evidence is unavailable", async () => {
    const ready = mocks.get.getMockImplementation();
    mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
      if (path === "/api/v1/driver/vehicles/{vehicle_id}/evidence-current") {
        throw new ApiError(503, { code: "STORAGE_UNAVAILABLE", message: "unavailable" });
      }
      return ready?.(path, options);
    });

    const result = await loadDriverCampaignJourney();

    expect(result.journey.standing).toBe("DEGRADED");
    expect(result.trackerAssignment).toBeNull();
  });

  it("keeps the current trip identity manageable when activation is unavailable", async () => {
    const ready = mocks.get.getMockImplementation();
    mocks.get.mockImplementation(async (path: string, options?: Record<string, unknown>) => {
      if (path === "/api/v1/driver/campaign-assignments/active") {
        throw new ApiError(503, { code: "PROVIDER_UNAVAILABLE", message: "unavailable" });
      }
      if (path === "/api/v1/driver/trips/current") return { data: { trip: { id: TRIP_ID } } };
      return ready?.(path, options);
    });

    const result = await loadDriverCampaignJourney();

    expect(result.journey.standing).toBe("TRACKING");
    expect(result.currentTrip).toEqual({ id: TRIP_ID });
    expect(result.trackerAssignment).toBeNull();
  });
});
