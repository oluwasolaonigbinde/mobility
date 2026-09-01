/**
 * Durable ping queue (RM4/RM5): persistence, stable idempotency keys,
 * ACK-then-delete, reload recovery, and atomic cuts.
 */
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import { openPingQueue, type PingQueue } from "./ping-queue";

const TRIP = "11111111-1111-4111-8111-111111111111";
const OTHER_TRIP = "22222222-2222-4222-8222-222222222222";

function ping(offset = 0) {
  return {
    recorded_at: new Date(1_700_000_000_000 + offset * 1000).toISOString(),
    lat: 6.45,
    lon: 3.39,
    accuracy_m: 10,
    speed_mps: 5,
    heading_degrees: 90,
  };
}

let queue: PingQueue;
let dbName: string;

function rawOpen(name: string, version?: number): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = version === undefined ? indexedDB.open(name) : indexedDB.open(name, version);
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
  tx.objectStore("pending").put({ tripId: TRIP, seq: 0, ping: { ...ping(0), sequence_number: 0 } });
  tx.objectStore("meta").put({ tripId: TRIP, nextSeq: 1, batchesCut: 0, pingsRecorded: 1 });
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

beforeEach(async () => {
  // Fresh IDB per test; unique name so closed handles never collide.
  (globalThis as { indexedDB: IDBFactory }).indexedDB = new IDBFactory();
  dbName = `test-queue-${Math.random().toString(36).slice(2)}`;
  queue = await openPingQueue(dbName);
});

describe("addPing", () => {
  it("assigns monotonic sequence numbers and tracks cumulative counts", async () => {
    const first = await queue.addPing(TRIP, ping(0));
    const second = await queue.addPing(TRIP, ping(1));
    expect(first.sequence_number).toBe(0);
    expect(second.sequence_number).toBe(1);
    const meta = await queue.meta(TRIP);
    expect(meta.nextSeq).toBe(2);
    expect(meta.pingsRecorded).toBe(2);
    expect(await queue.pendingCount(TRIP)).toBe(2);
  });

  it("keeps per-trip sequences independent", async () => {
    await queue.addPing(TRIP, ping(0));
    const other = await queue.addPing(OTHER_TRIP, ping(0));
    expect(other.sequence_number).toBe(0);
  });

  it("serializes concurrent additions without reusing a sequence or losing counters", async () => {
    const added = await Promise.all([queue.addPing(TRIP, ping(0)), queue.addPing(TRIP, ping(1))]);

    expect(added.map((item) => item.sequence_number).sort()).toEqual([0, 1]);
    expect(await queue.pendingCount(TRIP)).toBe(2);
    expect(await queue.meta(TRIP)).toMatchObject({ nextSeq: 2, pingsRecorded: 2 });
  });
});

describe("cutBatch", () => {
  it("moves pending pings into one batch with a minted key, atomically", async () => {
    await queue.addPing(TRIP, ping(0));
    await queue.addPing(TRIP, ping(1));
    const batch = await queue.cutBatch(TRIP);
    expect(batch).not.toBeNull();
    expect(batch!.pings.map((p) => p.sequence_number)).toEqual([0, 1]);
    expect(batch!.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(await queue.pendingCount(TRIP)).toBe(0);
    expect((await queue.meta(TRIP)).batchesCut).toBe(1);
  });

  it("returns null when there is nothing to cut and does not bump counters", async () => {
    expect(await queue.cutBatch(TRIP)).toBeNull();
    expect((await queue.meta(TRIP)).batchesCut).toBe(0);
  });

  it("respects the max size and preserves cut order across batches", async () => {
    for (let i = 0; i < 5; i += 1) await queue.addPing(TRIP, ping(i));
    const a = await queue.cutBatch(TRIP, 3);
    const b = await queue.cutBatch(TRIP, 3);
    expect(a!.pings).toHaveLength(3);
    expect(b!.pings).toHaveLength(2);
    const listed = await queue.listBatches(TRIP);
    expect(listed.map((batch) => batch.key)).toEqual([a!.key, b!.key]);
    expect((await queue.meta(TRIP)).batchesCut).toBe(2);
  });

  it("RM4: the key survives retries — recordAttempt never re-mints", async () => {
    await queue.addPing(TRIP, ping(0));
    const batch = await queue.cutBatch(TRIP);
    await queue.recordAttempt(batch!.key);
    await queue.recordAttempt(batch!.key);
    const [stored] = await queue.listBatches(TRIP);
    expect(stored!.key).toBe(batch!.key);
    expect(stored!.attempts).toBe(2);
    expect(stored!.pings).toEqual(batch!.pings);
  });

  it("serializes an addition racing a cut without losing or duplicating evidence", async () => {
    await queue.addPing(TRIP, ping(0));

    const [added, batch] = await Promise.all([queue.addPing(TRIP, ping(1)), queue.cutBatch(TRIP)]);
    const pendingBatch = await queue.cutBatch(TRIP);
    const sequences = [...(batch?.pings ?? []), ...(pendingBatch?.pings ?? [])]
      .map((item) => item.sequence_number)
      .sort();

    expect(added.sequence_number).toBe(1);
    expect(sequences).toEqual([0, 1]);
    expect(await queue.meta(TRIP)).toMatchObject({
      nextSeq: 2,
      pingsRecorded: 2,
      batchesCut: 1,
    });
  });
});

describe("ACK semantics", () => {
  it("ackBatch deletes (server holds the data: accepted, duplicate, or quarantined)", async () => {
    await queue.addPing(TRIP, ping(0));
    const batch = await queue.cutBatch(TRIP);
    await queue.ackBatch(batch!.key);
    expect(await queue.listBatches(TRIP)).toHaveLength(0);
    expect(await queue.unsyncedCount(TRIP)).toBe(0);
    // Cumulative counters survive the ACK — they back the end watermark.
    const meta = await queue.meta(TRIP);
    expect(meta.batchesCut).toBe(1);
    expect(meta.pingsRecorded).toBe(1);
  });

  it("terminal rejection retains the exact batch as durable diagnostic evidence", async () => {
    await queue.addPing(TRIP, ping(0));
    const dead = await queue.cutBatch(TRIP);
    await queue.addPing(TRIP, ping(1));
    const alive = await queue.cutBatch(TRIP);
    await queue.dropBatch(dead!.key);
    expect((await queue.listBatches(TRIP)).map((b) => b.key)).toEqual([alive!.key]);
    expect(await queue.listDeadLetters(TRIP)).toEqual([
      expect.objectContaining({
        key: dead!.key,
        tripId: TRIP,
        cutSeq: dead!.cutSeq,
        pings: dead!.pings,
      }),
    ]);
  });
});

describe("driver identity isolation", () => {
  it("does not enumerate another driver's leftovers on the same origin", async () => {
    const openForDriver = openPingQueue as unknown as (options: {
      dbName: string;
      driverId: string;
      requireMigrationLock: boolean;
    }) => Promise<PingQueue>;
    queue.close();
    const options = { dbName, driverId: "driver-a", requireMigrationLock: false };
    const first = await openForDriver(options);
    await first.addPing(TRIP, ping(0));
    first.close();

    options.driverId = "driver-b";
    const second = await openForDriver(options);
    expect(await second.tripsWithLeftovers()).toEqual([]);
    second.close();
  });
});

describe("encrypted at-rest state", () => {
  it("stores coordinates only as ciphertext under a non-extractable key", async () => {
    await queue.addPing(TRIP, ping(0));
    const raw = await rawOpen(dbName);
    const records = await requestResult(
      raw.transaction("encrypted-records", "readonly").objectStore("encrypted-records").getAll(),
    );
    const keyRows = (await requestResult(
      raw.transaction("encryption-keys", "readonly").objectStore("encryption-keys").getAll(),
    )) as Array<{ key: CryptoKey }>;
    expect(JSON.stringify(records)).not.toContain("6.45");
    expect(JSON.stringify(records)).not.toContain('"lat"');
    expect(keyRows[0]?.key.extractable).toBe(false);
    raw.close();
  });

  it("fails closed when ciphertext is tampered", async () => {
    await queue.addPing(TRIP, ping(0));
    const raw = await rawOpen(dbName);
    const tx = raw.transaction("encrypted-records", "readwrite");
    const store = tx.objectStore("encrypted-records");
    const records = (await requestResult(store.getAll())) as Array<{
      kind: string;
      ciphertext: ArrayBuffer;
      [key: string]: unknown;
    }>;
    const pending = records.find((record) => record.kind === "pending")!;
    const bytes = new Uint8Array(pending.ciphertext.slice(0));
    bytes[0] = (bytes[0] ?? 0) ^ 1;
    store.put({ ...pending, ciphertext: bytes.buffer });
    await new Promise<void>((resolve) => {
      tx.oncomplete = () => resolve();
    });
    raw.close();
    await expect(queue.cutBatch(TRIP)).rejects.toThrow();
  });

  it("fails closed instead of replacing a missing driver key", async () => {
    await queue.addPing(TRIP, ping(0));
    queue.close();
    const raw = await rawOpen(dbName);
    const tx = raw.transaction("encryption-keys", "readwrite");
    tx.objectStore("encryption-keys").delete("__isolated_capability_probe__");
    await new Promise<void>((resolve) => {
      tx.oncomplete = () => resolve();
    });
    raw.close();
    await expect(openPingQueue(dbName)).rejects.toThrow(/key is missing/i);
  });
});

describe("serialized legacy migration", () => {
  it("upgrades the v1 production default database in place", async () => {
    queue.close();
    const historicalDefault = "cardvert-ping-queue";
    await seedLegacyV1(historicalDefault);

    const migrated = await openPingQueue({
      driverId: "driver-a",
      requireMigrationLock: false,
      verifyTripOwner: async () => "owned",
    });
    expect(await migrated.tripsWithLeftovers()).toEqual([TRIP]);
    expect(await migrated.meta(TRIP)).toMatchObject({ nextSeq: 1, pingsRecorded: 1 });
    migrated.close();

    const raw = await rawOpen(historicalDefault);
    expect(
      await requestResult(raw.transaction("pending", "readonly").objectStore("pending").count()),
    ).toBe(0);
    const encrypted = (await requestResult(
      raw.transaction("encrypted-records", "readonly").objectStore("encrypted-records").getAll(),
    )) as Array<{ ownerDriverId: string | null }>;
    expect(encrypted.length).toBeGreaterThan(0);
    expect(encrypted.every((record) => record.ownerDriverId === "driver-a")).toBe(true);
    expect(JSON.stringify(encrypted)).not.toContain("6.45");
    expect(JSON.stringify(encrypted)).not.toContain('"lat"');
    raw.close();
  });

  it("encrypts v1 plaintext, preserves counters and resumes owner binding after interruption", async () => {
    queue.close();
    const legacyName = `${dbName}-legacy`;
    await seedLegacyV1(legacyName);
    await expect(
      openPingQueue({
        dbName: legacyName,
        driverId: "driver-a",
        requireMigrationLock: false,
        verifyTripOwner: async () => "unavailable",
      }),
    ).rejects.toThrow(/ownership could not be verified/i);

    const raw = await rawOpen(legacyName);
    expect(
      await requestResult(raw.transaction("pending", "readonly").objectStore("pending").count()),
    ).toBe(0);
    const encrypted = (await requestResult(
      raw.transaction("encrypted-records", "readonly").objectStore("encrypted-records").getAll(),
    )) as Array<{ ownerDriverId: string | null }>;
    expect(JSON.stringify(encrypted)).not.toContain("6.45");
    expect(encrypted.every((record) => record.ownerDriverId === null)).toBe(true);
    const journal = (await requestResult(
      raw
        .transaction("migration-journal", "readonly")
        .objectStore("migration-journal")
        .get("legacy-v1"),
    )) as { phase: string };
    expect(journal.phase).toBe("binding");
    raw.close();

    const resumed = await openPingQueue({
      dbName: legacyName,
      driverId: "driver-a",
      requireMigrationLock: false,
      verifyTripOwner: async () => "owned",
    });
    expect(await resumed.tripsWithLeftovers()).toEqual([TRIP]);
    expect(await resumed.meta(TRIP)).toMatchObject({ nextSeq: 1, pingsRecorded: 1 });
    const added = await resumed.addPing(TRIP, ping(1));
    expect(added.sequence_number).toBe(1);
    const batch = await resumed.cutBatch(TRIP);
    expect(batch?.pings.map((item) => item.sequence_number)).toEqual([0, 1]);
    expect(await resumed.meta(TRIP)).toMatchObject({
      nextSeq: 2,
      pingsRecorded: 2,
      batchesCut: 1,
    });
    resumed.close();
  });

  it("keeps mismatched legacy state encrypted-unbound and invisible until its owner reauthenticates", async () => {
    queue.close();
    const legacyName = `${dbName}-legacy`;
    await seedLegacyV1(legacyName);
    const other = await openPingQueue({
      dbName: legacyName,
      driverId: "driver-b",
      requireMigrationLock: false,
      verifyTripOwner: async () => "not-owned",
    });
    expect(await other.tripsWithLeftovers()).toEqual([]);
    other.close();

    const raw = await rawOpen(legacyName);
    const encrypted = (await requestResult(
      raw.transaction("encrypted-records", "readonly").objectStore("encrypted-records").getAll(),
    )) as Array<{ ownerDriverId: string | null }>;
    const journal = (await requestResult(
      raw
        .transaction("migration-journal", "readonly")
        .objectStore("migration-journal")
        .get("legacy-v1"),
    )) as { phase: string };
    expect(encrypted.every((record) => record.ownerDriverId === null)).toBe(true);
    expect(journal.phase).toBe("complete");
    raw.close();

    const owner = await openPingQueue({
      dbName: legacyName,
      driverId: "driver-a",
      requireMigrationLock: false,
      verifyTripOwner: async () => "owned",
    });
    expect(await owner.tripsWithLeftovers()).toEqual([TRIP]);
    owner.close();
  });

  it("requires the migration Web Lock for production-scoped opens", async () => {
    queue.close();
    await expect(openPingQueue({ dbName, driverId: "driver-a" })).rejects.toThrow(/Web Locks/);
  });
});

describe("reload recovery (RM5)", () => {
  it("pending pings, unsent batches, and the sequence survive a reopen", async () => {
    await queue.addPing(TRIP, ping(0));
    const batch = await queue.cutBatch(TRIP);
    await queue.addPing(TRIP, ping(1));
    queue.close();

    const reopened = await openPingQueue(dbName);
    expect((await reopened.listBatches(TRIP)).map((b) => b.key)).toEqual([batch!.key]);
    expect(await reopened.pendingCount(TRIP)).toBe(1);
    const next = await reopened.addPing(TRIP, ping(2));
    expect(next.sequence_number).toBe(2); // monotonic across reloads
    expect(await reopened.tripsWithLeftovers()).toEqual([TRIP]);
    reopened.close();
  });
});

describe("forgetTrip", () => {
  it("clears every store for the trip and leaves other trips alone", async () => {
    await queue.addPing(TRIP, ping(0));
    await queue.cutBatch(TRIP);
    await queue.addPing(OTHER_TRIP, ping(0));
    await queue.forgetTrip(TRIP);
    expect(await queue.unsyncedCount(TRIP)).toBe(0);
    expect((await queue.meta(TRIP)).nextSeq).toBe(0);
    expect(await queue.pendingCount(OTHER_TRIP)).toBe(1);
  });
});
