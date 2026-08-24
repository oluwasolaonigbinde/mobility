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

  it("dropBatch removes a dead batch so it cannot jam the queue", async () => {
    await queue.addPing(TRIP, ping(0));
    const dead = await queue.cutBatch(TRIP);
    await queue.addPing(TRIP, ping(1));
    const alive = await queue.cutBatch(TRIP);
    await queue.dropBatch(dead!.key);
    expect((await queue.listBatches(TRIP)).map((b) => b.key)).toEqual([alive!.key]);
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
