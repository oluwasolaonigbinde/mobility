import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import {
  getCurrentTripAction,
  sendPingBatchAction,
  startTripAction,
  verifyDriverTripOwnershipAction,
} from "./actions";

const mocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn().mockResolvedValue("token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, GET: mocks.get, PATCH: vi.fn() }),
}));

const TRIP_ID = "11111111-1111-4111-8111-111111111111";
const ASSIGNMENT_ID = "22222222-2222-4222-8222-222222222222";

describe("driver trip BFF actions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("classifies proven Start rejection separately from an unknown response", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(422, { code: "VALIDATION_ERROR", message: "not eligible" }),
    );
    await expect(startTripAction(ASSIGNMENT_ID)).resolves.toMatchObject({ outcome: "failed" });

    mocks.post.mockRejectedValueOnce(
      new ApiError(409, { code: "ACTIVE_TRIP_EXISTS", message: "maybe committed" }),
    );
    await expect(startTripAction(ASSIGNMENT_ID)).resolves.toMatchObject({ outcome: "unknown" });

    mocks.post.mockRejectedValueOnce(new Error("response lost"));
    await expect(startTripAction(ASSIGNMENT_ID)).resolves.toMatchObject({ outcome: "unknown" });
  });

  it("uses current-trip authority to prove a missing or recovered Start", async () => {
    mocks.get.mockResolvedValueOnce({ data: { trip: { id: TRIP_ID } } });
    await expect(getCurrentTripAction()).resolves.toMatchObject({
      outcome: "started",
      trip: { id: TRIP_ID },
    });

    mocks.get.mockRejectedValueOnce(new ApiError(404, { code: "NOT_FOUND", message: "none" }));
    await expect(getCurrentTripAction()).resolves.toEqual({ outcome: "failed" });
  });

  it("returns terminal status/code so the exact encrypted batch can be dead-lettered", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, { code: "IDEMPOTENCY_CONFLICT", message: "conflict" }),
    );
    await expect(
      sendPingBatchAction({
        tripId: TRIP_ID,
        idempotencyKey: "stable-retry-key",
        pings: [
          {
            recorded_at: "2026-08-25T00:00:00.000Z",
            lat: 6.45,
            lon: 3.39,
            accuracy_m: 10,
            speed_mps: 5,
            heading_degrees: 90,
            sequence_number: 0,
          },
        ],
      }),
    ).resolves.toMatchObject({
      retryable: false,
      terminalStatus: 409,
      terminalCode: "IDEMPOTENCY_CONFLICT",
    });
  });

  it("verifies legacy trip ownership only through the owner-scoped BFF", async () => {
    mocks.get.mockResolvedValueOnce({ data: { id: TRIP_ID } });
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe(true);
    mocks.get.mockRejectedValueOnce(new ApiError(404, { code: "NOT_FOUND", message: "none" }));
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe(false);
  });
});
