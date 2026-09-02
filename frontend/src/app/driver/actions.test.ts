import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, toApiError } from "@/lib/api/errors";
import { openPingQueue } from "@/lib/trips/ping-queue";
import {
  endTripAction,
  getCurrentTripAction,
  reconcileTripEvidenceAction,
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
const EMPTY_MANIFEST = {
  version: 2 as const,
  root_sha256: "a".repeat(64),
  ping_count: 0,
  complete: true,
  entries: [],
};
const ACK_FIELDS = {
  submitted_count: 1,
  rejected_count: 0,
  batch_sequence: 0,
  payload_hash_version: 2,
  payload_hash: "b".repeat(64),
  outcome: "accepted",
  receipt_format_version: 2,
  receipt_key_version: 1,
  receipt_signature: "signed-receipt",
};

function rawOpen(name: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function seedLegacyV1(name: string): Promise<void> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("pending", { keyPath: ["tripId", "seq"] });
      request.result.createObjectStore("batches", { keyPath: "key" });
      request.result.createObjectStore("meta", { keyPath: "tripId" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const tx = db.transaction(["pending", "meta"], "readwrite");
  tx.objectStore("pending").put({
    tripId: TRIP_ID,
    seq: 0,
    ping: {
      recorded_at: "2026-08-25T00:00:00.000Z",
      lat: 6.45,
      lon: 3.39,
      accuracy_m: 10,
      speed_mps: 5,
      heading_degrees: 90,
      sequence_number: 0,
    },
  });
  tx.objectStore("meta").put({
    tripId: TRIP_ID,
    nextSeq: 1,
    batchesCut: 0,
    pingsRecorded: 1,
  });
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

describe("driver trip BFF actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (globalThis as { indexedDB: IDBFactory }).indexedDB = new IDBFactory();
  });

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
    mocks.get.mockResolvedValueOnce({
      data: { trip: { id: TRIP_ID, evidence_protocol_version: 2 } },
    });
    await expect(getCurrentTripAction()).resolves.toMatchObject({
      outcome: "started",
      trip: { id: TRIP_ID },
    });

    mocks.get.mockRejectedValueOnce(new ApiError(404, { code: "NOT_FOUND", message: "none" }));
    await expect(getCurrentTripAction()).resolves.toEqual({ outcome: "failed" });
  });

  it("returns only opaque trip identity from Start, current-trip and End actions", async () => {
    const rawTrip = {
      id: TRIP_ID,
      status: "active",
      evidence_protocol_version: 2,
      metadata: { internal: "must-not-cross" },
      driver_profile_id: "33333333-3333-4333-8333-333333333333",
    };
    mocks.post.mockResolvedValueOnce({ data: rawTrip });
    await expect(startTripAction(ASSIGNMENT_ID)).resolves.toEqual({
      trip: { id: TRIP_ID, evidenceProtocolVersion: 2 },
      outcome: "started",
    });

    mocks.get.mockResolvedValueOnce({ data: { trip: rawTrip } });
    await expect(getCurrentTripAction()).resolves.toEqual({
      trip: { id: TRIP_ID, evidenceProtocolVersion: 2 },
      outcome: "started",
    });

    mocks.post.mockResolvedValueOnce({ data: { ...rawTrip, status: "ended" } });
    await expect(endTripAction(TRIP_ID, EMPTY_MANIFEST)).resolves.toEqual({
      outcome: "ended",
      status: "ended",
    });

    mocks.post.mockResolvedValueOnce({ data: { ...rawTrip, status: "sealed" } });
    await expect(endTripAction(TRIP_ID, EMPTY_MANIFEST)).resolves.toEqual({
      outcome: "ended",
      status: "sealed",
    });
  });

  it("returns terminal status/code so the exact encrypted batch can be dead-lettered", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, { code: "IDEMPOTENCY_CONFLICT", message: "conflict" }),
    );
    await expect(
      sendPingBatchAction({
        tripId: TRIP_ID,
        evidenceProtocolVersion: 2,
        idempotencyKey: "stable-retry-key",
        batchSequence: 0,
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

  it("marks only a complete ping response as an explicit ACK", async () => {
    const input = {
      tripId: TRIP_ID,
      evidenceProtocolVersion: 2 as const,
      idempotencyKey: "stable-retry-key",
      batchSequence: 0,
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
    };
    mocks.post.mockResolvedValueOnce({
      data: {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        accepted_count: 1,
        ...ACK_FIELDS,
        duplicate: false,
        quarantined: false,
      },
    });
    await expect(sendPingBatchAction(input)).resolves.toMatchObject({ acknowledged: true });

    mocks.post.mockResolvedValueOnce({ data: undefined });
    await expect(sendPingBatchAction(input)).resolves.toMatchObject({
      acknowledged: false,
      retryable: true,
    });

    mocks.post.mockResolvedValueOnce({
      data: {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        accepted_count: 0,
        duplicate: false,
        quarantined: false,
      },
    });
    await expect(sendPingBatchAction(input)).resolves.toMatchObject({
      acknowledged: false,
      retryable: true,
    });
  });

  it("retains legacy evidence until a complete positive acknowledgement arrives", async () => {
    const input = {
      tripId: TRIP_ID,
      evidenceProtocolVersion: 1 as const,
      idempotencyKey: "stable-retry-key",
      batchSequence: 0,
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
    };
    for (const data of [
      { trip_id: TRIP_ID },
      {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        submitted_count: 1,
        accepted_count: 0,
        rejected_count: 1,
        duplicate: false,
        quarantined: false,
      },
    ]) {
      mocks.post.mockResolvedValueOnce({ data });
      await expect(sendPingBatchAction(input)).resolves.toMatchObject({
        acknowledged: false,
        retryable: true,
      });
    }

    for (const data of [
      {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        submitted_count: 1,
        accepted_count: 1,
        rejected_count: 0,
        duplicate: false,
        quarantined: false,
      },
      {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        submitted_count: 1,
        accepted_count: 0,
        rejected_count: 0,
        duplicate: true,
        quarantined: false,
      },
      {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        submitted_count: 1,
        accepted_count: 0,
        rejected_count: 1,
        duplicate: false,
        quarantined: true,
      },
    ]) {
      mocks.post.mockResolvedValueOnce({ data });
      await expect(sendPingBatchAction(input)).resolves.toMatchObject({ acknowledged: true });
    }
  });

  it("classifies evidence reconciliation from the sealed authority response", async () => {
    mocks.post.mockResolvedValueOnce({ data: { status: "sealed" } });
    await expect(reconcileTripEvidenceAction(TRIP_ID)).resolves.toEqual({
      outcome: "ended",
      status: "sealed",
    });

    mocks.post.mockResolvedValueOnce({ data: { status: "ended" } });
    await expect(reconcileTripEvidenceAction(TRIP_ID)).resolves.toMatchObject({
      outcome: "unknown",
    });

    mocks.post.mockRejectedValueOnce(
      new ApiError(409, { code: "TRIP_EVIDENCE_INCOMPLETE", message: "incomplete" }),
    );
    await expect(reconcileTripEvidenceAction(TRIP_ID)).resolves.toMatchObject({
      outcome: "failed",
    });
  });

  it("classifies an unconfirmed End response as unknown", async () => {
    mocks.post.mockResolvedValueOnce({ data: undefined });

    await expect(endTripAction(TRIP_ID, EMPTY_MANIFEST)).resolves.toMatchObject({
      outcome: "unknown",
    });
  });

  it.each([
    ["accepted", { accepted_count: 1, duplicate: false, quarantined: false }],
    ["duplicate", { accepted_count: 1, duplicate: true, quarantined: false }],
    ["quarantined", { accepted_count: 0, duplicate: false, quarantined: true }],
  ])("treats a complete %s response as an ACK", async (_label, response) => {
    mocks.post.mockResolvedValueOnce({
      data: {
        batch_id: "44444444-4444-4444-8444-444444444444",
        trip_id: TRIP_ID,
        ...ACK_FIELDS,
        ...response,
      },
    });

    await expect(
      sendPingBatchAction({
        tripId: TRIP_ID,
        evidenceProtocolVersion: 2,
        idempotencyKey: "stable-retry-key",
        batchSequence: 0,
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
      acknowledged: true,
      acceptedCount: response.accepted_count,
      duplicate: response.duplicate,
      quarantined: response.quarantined,
    });
  });

  it("verifies legacy trip ownership only through the owner-scoped BFF", async () => {
    mocks.get.mockResolvedValueOnce({ data: { id: TRIP_ID } });
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("owned");
    mocks.get.mockRejectedValueOnce(new ApiError(404, { code: "TRIP_NOT_FOUND", message: "none" }));
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("not-owned");

    for (const error of [
      new ApiError(404, { code: "DRIVER_PROFILE_NOT_FOUND", message: "none" }),
      new ApiError(404, { code: "NOT_FOUND", message: "none" }),
      new ApiError(404, { code: "UNEXPECTED_ERROR", message: "none" }),
      toApiError(404, { error: { message: "none" } }),
    ]) {
      mocks.get.mockRejectedValueOnce(error);
      await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("unavailable");
    }

    mocks.get.mockRejectedValueOnce(new Error("provider unavailable"));
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("unavailable");
    mocks.get.mockRejectedValueOnce(
      new ApiError(401, { code: "UNAUTHORIZED", message: "expired" }),
    );
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("unavailable");
    mocks.get.mockResolvedValueOnce({ data: undefined });
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("unavailable");
    mocks.get.mockResolvedValueOnce({ data: { id: ASSIGNMENT_ID } });
    await expect(verifyDriverTripOwnershipAction(TRIP_ID)).resolves.toBe("unavailable");
    await expect(verifyDriverTripOwnershipAction("invalid-trip-id")).resolves.toBe("unavailable");
  });

  it("fails queue on outage, isolates a proven non-owner, then binds without collision", async () => {
    const dbName = "action-queue-composition";
    await seedLegacyV1(dbName);
    mocks.get.mockRejectedValueOnce(
      new ApiError(404, { code: "DRIVER_PROFILE_NOT_FOUND", message: "none" }),
    );

    await expect(
      openPingQueue({
        dbName,
        driverId: "driver-a",
        requireMigrationLock: false,
        verifyTripOwner: verifyDriverTripOwnershipAction,
      }),
    ).rejects.toThrow(/ownership could not be verified/i);

    const raw = await rawOpen(dbName);
    const encrypted = (await requestResult(
      raw.transaction("encrypted-records", "readonly").objectStore("encrypted-records").getAll(),
    )) as Array<{ ownerDriverId: string | null }>;
    const journal = (await requestResult(
      raw
        .transaction("migration-journal", "readonly")
        .objectStore("migration-journal")
        .get("legacy-v1"),
    )) as { phase: string };
    expect(encrypted).toHaveLength(2);
    expect(encrypted.every((record) => record.ownerDriverId === null)).toBe(true);
    expect(journal.phase).toBe("binding");
    raw.close();

    mocks.get.mockRejectedValueOnce(new ApiError(404, { code: "TRIP_NOT_FOUND", message: "none" }));
    const isolated = await openPingQueue({
      dbName,
      driverId: "driver-b",
      requireMigrationLock: false,
      verifyTripOwner: verifyDriverTripOwnershipAction,
    });
    expect(await isolated.tripsWithLeftovers()).toEqual([]);
    isolated.close();

    mocks.get.mockResolvedValueOnce({ data: { id: TRIP_ID } });
    const recovered = await openPingQueue({
      dbName,
      driverId: "driver-a",
      requireMigrationLock: false,
      verifyTripOwner: verifyDriverTripOwnershipAction,
    });
    expect(await recovered.tripsWithLeftovers()).toEqual([TRIP_ID]);
    const added = await recovered.addPing(TRIP_ID, {
      recorded_at: "2026-08-25T00:00:01.000Z",
      lat: 6.46,
      lon: 3.4,
      accuracy_m: 11,
      speed_mps: 6,
      heading_degrees: 91,
    });
    expect(added.sequence_number).toBe(1);
    const batch = await recovered.cutBatch(TRIP_ID);
    expect(batch?.pings.map((item) => item.sequence_number)).toEqual([0, 1]);
    expect(await recovered.meta(TRIP_ID)).toMatchObject({
      nextSeq: 2,
      pingsRecorded: 2,
      batchesCut: 1,
    });
    recovered.close();
  });
});
