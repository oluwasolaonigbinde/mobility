/**
 * Durable driver ping queue (RM4/RM5).
 *
 * IndexedDB-backed so unsent GPS points survive reloads, crashes, and phone
 * restarts. Three stores:
 *
 * - `pending` — individual pings, persisted the moment they are recorded,
 *   keyed [tripId, seq]. `seq` is monotonic per trip and survives reload.
 * - `batches` — cut batches awaiting upload. The idempotency key is minted
 *   ONCE at cut time and reused verbatim for every retry (RM4): a batch that
 *   persisted server-side but whose response was lost dedupes instead of
 *   double-inserting.
 * - `meta` — per-trip durable counters: next sequence number plus cumulative
 *   `batchesCut` / `pingsRecorded`, which back the trip-end watermark (RM3).
 *   Cumulative counts live here because ACKed batches are deleted — surviving
 *   rows cannot reconstruct them.
 *
 * The cut operation (pending → batch + counter bump) runs in ONE readwrite
 * transaction across all three stores: a crash mid-cut can never lose pings
 * or re-cut the same pings into a second batch under a new key.
 *
 * Upload ACK semantics: success, `duplicate: true`, and `quarantined: true`
 * all delete the batch — in every case the server durably holds the data.
 */

export interface QueuedPing {
  recorded_at: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  speed_mps: number | null;
  heading_degrees: number | null;
  sequence_number: number;
}

export interface QueuedBatch {
  /** Idempotency key — minted once at cut time, stable across retries. */
  key: string;
  tripId: string;
  /** Monotonic per-trip cut index — the stable upload order. */
  cutSeq: number;
  cutAt: number;
  attempts: number;
  pings: QueuedPing[];
}

export interface TripMeta {
  tripId: string;
  nextSeq: number;
  batchesCut: number;
  pingsRecorded: number;
}

const DB_VERSION = 1;
export const DEFAULT_DB_NAME = "vantage-ping-queue";

function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
  });
}

export class PingQueue {
  constructor(private readonly db: IDBDatabase) {}

  /** Persist a ping immediately; assigns the trip's next sequence number. */
  async addPing(
    tripId: string,
    ping: Omit<QueuedPing, "sequence_number">,
  ): Promise<QueuedPing> {
    const tx = this.db.transaction(["pending", "meta"], "readwrite");
    const metaStore = tx.objectStore("meta");
    const meta =
      ((await promisify(metaStore.get(tripId))) as TripMeta | undefined) ?? {
        tripId,
        nextSeq: 0,
        batchesCut: 0,
        pingsRecorded: 0,
      };
    const queued: QueuedPing = { ...ping, sequence_number: meta.nextSeq };
    tx.objectStore("pending").put({ tripId, seq: meta.nextSeq, ping: queued });
    metaStore.put({
      ...meta,
      nextSeq: meta.nextSeq + 1,
      pingsRecorded: meta.pingsRecorded + 1,
    });
    await transactionDone(tx);
    return queued;
  }

  /**
   * Atomically move up to `max` pending pings into a new batch with a
   * freshly minted (then permanent) idempotency key. Returns null when there
   * is nothing to cut.
   */
  async cutBatch(tripId: string, max = 40): Promise<QueuedBatch | null> {
    const tx = this.db.transaction(["pending", "batches", "meta"], "readwrite");
    const pendingStore = tx.objectStore("pending");
    const range = IDBKeyRange.bound([tripId, 0], [tripId, Number.MAX_SAFE_INTEGER]);
    const rows = (await promisify(pendingStore.getAll(range, max))) as Array<{
      tripId: string;
      seq: number;
      ping: QueuedPing;
    }>;
    if (rows.length === 0) {
      tx.abort();
      return null;
    }
    const metaStore = tx.objectStore("meta");
    const meta = (await promisify(metaStore.get(tripId))) as TripMeta | undefined;
    const batch: QueuedBatch = {
      key: crypto.randomUUID(),
      tripId,
      cutSeq: meta?.batchesCut ?? 0,
      cutAt: Date.now(),
      attempts: 0,
      pings: rows.map((row) => row.ping),
    };
    tx.objectStore("batches").put(batch);
    for (const row of rows) {
      pendingStore.delete([row.tripId, row.seq]);
    }
    const lastSeq = rows[rows.length - 1]?.seq ?? 0;
    metaStore.put({
      tripId,
      nextSeq: meta?.nextSeq ?? lastSeq + 1,
      batchesCut: (meta?.batchesCut ?? 0) + 1,
      pingsRecorded: meta?.pingsRecorded ?? rows.length,
    });
    await transactionDone(tx);
    return batch;
  }

  /** Unsent batches for a trip (or every trip), oldest cut first. */
  async listBatches(tripId?: string): Promise<QueuedBatch[]> {
    const tx = this.db.transaction("batches", "readonly");
    const all = (await promisify(tx.objectStore("batches").getAll())) as QueuedBatch[];
    return all
      .filter((batch) => tripId === undefined || batch.tripId === tripId)
      .sort(
        (a, b) =>
          a.tripId.localeCompare(b.tripId) || a.cutSeq - b.cutSeq || a.cutAt - b.cutAt,
      );
  }

  /** ACK: the server durably holds this batch (accepted, duplicate, or quarantined). */
  async ackBatch(key: string): Promise<void> {
    const tx = this.db.transaction("batches", "readwrite");
    tx.objectStore("batches").delete(key);
    await transactionDone(tx);
  }

  /** Drop a batch the server terminally rejected (dead letter — RM review #5). */
  async dropBatch(key: string): Promise<void> {
    await this.ackBatch(key);
  }

  async recordAttempt(key: string): Promise<void> {
    const tx = this.db.transaction("batches", "readwrite");
    const store = tx.objectStore("batches");
    const batch = (await promisify(store.get(key))) as QueuedBatch | undefined;
    if (batch) store.put({ ...batch, attempts: batch.attempts + 1 });
    await transactionDone(tx);
  }

  async pendingCount(tripId: string): Promise<number> {
    const tx = this.db.transaction("pending", "readonly");
    const range = IDBKeyRange.bound([tripId, 0], [tripId, Number.MAX_SAFE_INTEGER]);
    return promisify(tx.objectStore("pending").count(range));
  }

  /** Everything not yet ACKed for this trip: pending pings + cut-but-unsent. */
  async unsyncedCount(tripId: string): Promise<number> {
    const pending = await this.pendingCount(tripId);
    const batches = await this.listBatches(tripId);
    return pending + batches.reduce((sum, batch) => sum + batch.pings.length, 0);
  }

  async meta(tripId: string): Promise<TripMeta> {
    const tx = this.db.transaction("meta", "readonly");
    const meta = (await promisify(tx.objectStore("meta").get(tripId))) as
      | TripMeta
      | undefined;
    return meta ?? { tripId, nextSeq: 0, batchesCut: 0, pingsRecorded: 0 };
  }

  /** Trips that still have leftover data — used to drain after a reload. */
  async tripsWithLeftovers(): Promise<string[]> {
    const tx = this.db.transaction(["pending", "batches"], "readonly");
    const pendingRows = (await promisify(tx.objectStore("pending").getAll())) as Array<{
      tripId: string;
    }>;
    const batchRows = (await promisify(tx.objectStore("batches").getAll())) as QueuedBatch[];
    const ids = new Set<string>();
    for (const row of pendingRows) ids.add(row.tripId);
    for (const batch of batchRows) ids.add(batch.tripId);
    return [...ids];
  }

  /** Remove a trip's bookkeeping once fully drained (keeps the DB tidy). */
  async forgetTrip(tripId: string): Promise<void> {
    const tx = this.db.transaction(["pending", "batches", "meta"], "readwrite");
    const range = IDBKeyRange.bound([tripId, 0], [tripId, Number.MAX_SAFE_INTEGER]);
    tx.objectStore("pending").delete(range);
    const batchStore = tx.objectStore("batches");
    const batches = (await promisify(batchStore.getAll())) as QueuedBatch[];
    for (const batch of batches) {
      if (batch.tripId === tripId) batchStore.delete(batch.key);
    }
    tx.objectStore("meta").delete(tripId);
    await transactionDone(tx);
  }

  close(): void {
    this.db.close();
  }
}

export function openPingQueue(dbName: string = DEFAULT_DB_NAME): Promise<PingQueue> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("pending")) {
        db.createObjectStore("pending", { keyPath: ["tripId", "seq"] });
      }
      if (!db.objectStoreNames.contains("batches")) {
        db.createObjectStore("batches", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("meta")) {
        db.createObjectStore("meta", { keyPath: "tripId" });
      }
    };
    request.onsuccess = () => resolve(new PingQueue(request.result));
    request.onerror = () => reject(request.error);
  });
}
