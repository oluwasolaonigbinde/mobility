/**
 * Driver-scoped encrypted durable ping queue.
 *
 * Location-bearing records are AES-GCM encrypted before entering IndexedDB.
 * The non-extractable key, record namespace and AAD are all bound to the
 * server-verified driver id supplied by the guarded driver page. Version-one
 * plaintext databases are upgraded under a Web Lock, encrypted into an
 * unbound quarantine first, and only exposed after the owner-scoped trip BFF
 * verifies the current driver owns each trip.
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
  key: string;
  tripId: string;
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

export interface DeadLetter extends QueuedBatch {
  terminalStatus?: number;
  terminalCode?: string;
  rejectedAt?: number;
}

export type TripOwnershipVerification = "owned" | "not-owned" | "unavailable";

export interface OpenPingQueueOptions {
  driverId: string;
  dbName?: string;
  verifyTripOwner?: (tripId: string) => Promise<TripOwnershipVerification>;
  /** Test/probe-only injection; production callers must keep this true. */
  requireMigrationLock?: boolean;
}

type RecordKind = "pending" | "batch" | "meta";
type EncryptedRecord = {
  storageKey: string;
  ownerDriverId: string | null;
  tripId: string;
  kind: RecordKind;
  iv: Uint8Array<ArrayBuffer>;
  ciphertext: ArrayBuffer;
};
type KeyRecord = { id: string; key: CryptoKey };
type MigrationJournal = {
  id: "legacy-v1";
  phase: "encrypting" | "binding" | "complete";
  sourceFingerprint?: string;
};

const DB_VERSION = 2;
const RECORDS = "encrypted-records";
const DEAD_LETTERS = "encrypted-dead-letters";
const KEYS = "encryption-keys";
const MIGRATION = "migration-journal";
const LEGACY_STORES = ["pending", "batches", "meta"] as const;
const MIGRATION_LOCK = "cardvert-driver-storage-migration-v2";
const UNBOUND_KEY_ID = "__cardvert_legacy_unbound__";
const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

// Retain the shipped v1 name: v2 upgrades that production database in place.
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

function recordKey(driverId: string, kind: RecordKind, id: string): string {
  return `${driverId}\u001f${kind}\u001f${id}`;
}

function aad(
  owner: string | null,
  kind: RecordKind,
  tripId: string,
  storageKey: string,
): Uint8Array<ArrayBuffer> {
  return textEncoder.encode(
    `cardvert-driver-queue:v2:${owner ?? "unbound"}:${kind}:${tripId}:${storageKey}`,
  );
}

async function encryptPayload(
  key: CryptoKey,
  descriptor: Pick<EncryptedRecord, "storageKey" | "ownerDriverId" | "tripId" | "kind">,
  value: unknown,
): Promise<EncryptedRecord> {
  const iv = crypto.getRandomValues(new Uint8Array(new ArrayBuffer(12)));
  const ciphertext = await crypto.subtle.encrypt(
    {
      name: "AES-GCM",
      iv,
      additionalData: aad(
        descriptor.ownerDriverId,
        descriptor.kind,
        descriptor.tripId,
        descriptor.storageKey,
      ),
    },
    key,
    textEncoder.encode(JSON.stringify(value)),
  );
  return { ...descriptor, iv, ciphertext };
}

async function decryptPayload<T>(key: CryptoKey, record: EncryptedRecord): Promise<T> {
  const plaintext = await crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: record.iv,
      additionalData: aad(record.ownerDriverId, record.kind, record.tripId, record.storageKey),
    },
    key,
    record.ciphertext,
  );
  return JSON.parse(textDecoder.decode(plaintext)) as T;
}

async function createKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

async function getAll<T>(db: IDBDatabase, storeName: string): Promise<T[]> {
  const tx = db.transaction(storeName, "readonly");
  return (await promisify(tx.objectStore(storeName).getAll())) as T[];
}

async function loadKey(db: IDBDatabase, id: string): Promise<CryptoKey | undefined> {
  const tx = db.transaction(KEYS, "readonly");
  return ((await promisify(tx.objectStore(KEYS).get(id))) as KeyRecord | undefined)?.key;
}

async function putKey(db: IDBDatabase, id: string, key: CryptoKey): Promise<void> {
  const tx = db.transaction(KEYS, "readwrite");
  tx.objectStore(KEYS).put({ id, key } satisfies KeyRecord);
  await transactionDone(tx);
}

async function loadOrCreateDriverKey(db: IDBDatabase, driverId: string): Promise<CryptoKey> {
  const existing = await loadKey(db, driverId);
  if (existing) return existing;
  const records = [
    ...(await getAll<EncryptedRecord>(db, RECORDS)),
    ...(await getAll<EncryptedRecord>(db, DEAD_LETTERS)),
  ];
  if (records.some((record) => record.ownerDriverId === driverId)) {
    throw new Error("Encrypted driver data exists but its key is missing");
  }
  const key = await createKey();
  await putKey(db, driverId, key);
  return key;
}

function openDatabase(dbName: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, DB_VERSION);
    let blocked = false;
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(RECORDS)) {
        const records = db.createObjectStore(RECORDS, { keyPath: "storageKey" });
        records.createIndex("owner", "ownerDriverId", { unique: false });
      }
      if (!db.objectStoreNames.contains(DEAD_LETTERS)) {
        const deadLetters = db.createObjectStore(DEAD_LETTERS, { keyPath: "storageKey" });
        deadLetters.createIndex("owner", "ownerDriverId", { unique: false });
      }
      if (!db.objectStoreNames.contains(KEYS)) db.createObjectStore(KEYS, { keyPath: "id" });
      if (!db.objectStoreNames.contains(MIGRATION)) {
        db.createObjectStore(MIGRATION, { keyPath: "id" });
      }
    };
    request.onblocked = () => {
      blocked = true;
      reject(new Error("IndexedDB upgrade is blocked by another Cardvert tab"));
    };
    request.onsuccess = () => {
      const db = request.result;
      db.onversionchange = () => db.close();
      if (blocked) db.close();
      else resolve(db);
    };
    request.onerror = () => reject(request.error);
  });
}

async function sourceFingerprint(store: string, value: unknown): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    textEncoder.encode(`${store}:${JSON.stringify(value)}`),
  );
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function legacyDescriptor(store: (typeof LEGACY_STORES)[number], value: unknown) {
  if (store === "pending") {
    const row = value as { tripId: string; seq: number; ping: QueuedPing };
    return { tripId: row.tripId, kind: "pending" as const, payload: row.ping };
  }
  if (store === "batches") {
    const batch = value as QueuedBatch;
    return { tripId: batch.tripId, kind: "batch" as const, payload: batch };
  }
  const meta = value as TripMeta;
  return { tripId: meta.tripId, kind: "meta" as const, payload: meta };
}

async function migrateLegacy(
  db: IDBDatabase,
  driverId: string,
  driverKey: CryptoKey,
  verifyTripOwner?: (tripId: string) => Promise<TripOwnershipVerification>,
): Promise<void> {
  const present = LEGACY_STORES.filter((name) => db.objectStoreNames.contains(name));
  let unboundKey = await loadKey(db, UNBOUND_KEY_ID);
  const legacyRows = (
    await Promise.all(
      present.map(async (store) =>
        (await getAll<unknown>(db, store)).map((value) => ({ store, value })),
      ),
    )
  ).flat();
  if (legacyRows.length > 0 && !unboundKey) {
    unboundKey = await createKey();
    await putKey(db, UNBOUND_KEY_ID, unboundKey);
  }

  for (const { store, value } of legacyRows) {
    const descriptor = legacyDescriptor(store, value);
    const fingerprint = await sourceFingerprint(store, value);
    const storageKey = `legacy\u001f${fingerprint}`;
    const encrypted = await encryptPayload(
      unboundKey!,
      {
        storageKey,
        ownerDriverId: null,
        tripId: descriptor.tripId,
        kind: descriptor.kind,
      },
      descriptor.payload,
    );
    const tx = db.transaction([store, RECORDS, MIGRATION], "readwrite");
    tx.objectStore(RECORDS).put(encrypted);
    const legacyStore = tx.objectStore(store);
    if (store === "pending") {
      const row = value as { tripId: string; seq: number };
      legacyStore.delete([row.tripId, row.seq]);
    } else if (store === "batches") {
      legacyStore.delete((value as QueuedBatch).key);
    } else {
      legacyStore.delete((value as TripMeta).tripId);
    }
    tx.objectStore(MIGRATION).put({
      id: "legacy-v1",
      phase: "encrypting",
      sourceFingerprint: fingerprint,
    } satisfies MigrationJournal);
    await transactionDone(tx);
  }

  const unbound = (await getAll<EncryptedRecord>(db, RECORDS)).filter(
    (record) => record.ownerDriverId === null,
  );
  if (unbound.length > 0 && !unboundKey) {
    throw new Error("Encrypted legacy data exists but its migration key is missing");
  }
  if (unbound.length > 0) {
    const tx = db.transaction(MIGRATION, "readwrite");
    tx.objectStore(MIGRATION).put({ id: "legacy-v1", phase: "binding" } satisfies MigrationJournal);
    await transactionDone(tx);
  }
  const ownership = new Map<string, TripOwnershipVerification>();
  for (const record of unbound) {
    let verification = ownership.get(record.tripId);
    if (verification === undefined) {
      verification = verifyTripOwner ? await verifyTripOwner(record.tripId) : "unavailable";
      ownership.set(record.tripId, verification);
    }
    if (verification === "unavailable") {
      throw new Error("Legacy trip ownership could not be verified");
    }
    if (verification === "not-owned") continue;
    const payload = await decryptPayload<unknown>(unboundKey!, record);
    const logicalId =
      record.kind === "pending"
        ? `${record.tripId}:${String((payload as QueuedPing).sequence_number).padStart(16, "0")}`
        : record.kind === "batch"
          ? (payload as QueuedBatch).key
          : record.tripId;
    const storageKey = recordKey(driverId, record.kind, logicalId);
    const rebound = await encryptPayload(
      driverKey,
      { storageKey, ownerDriverId: driverId, tripId: record.tripId, kind: record.kind },
      payload,
    );
    const tx = db.transaction([RECORDS, MIGRATION], "readwrite");
    tx.objectStore(RECORDS).delete(record.storageKey);
    tx.objectStore(RECORDS).put(rebound);
    tx.objectStore(MIGRATION).put({ id: "legacy-v1", phase: "binding" } satisfies MigrationJournal);
    await transactionDone(tx);
  }
  if (legacyRows.length > 0 || unbound.length > 0) {
    const tx = db.transaction(MIGRATION, "readwrite");
    tx.objectStore(MIGRATION).put({
      id: "legacy-v1",
      phase: "complete",
    } satisfies MigrationJournal);
    await transactionDone(tx);
  }
}

async function withMigrationLock<T>(required: boolean, operation: () => Promise<T>): Promise<T> {
  if (!required) return operation();
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  if (!locks) throw new Error("Web Locks are required for encrypted queue migration");
  return locks.request(MIGRATION_LOCK, { mode: "exclusive" }, operation);
}

export class PingQueue {
  private mutationTail: Promise<void> = Promise.resolve();

  constructor(
    private readonly db: IDBDatabase,
    private readonly driverId: string,
    private readonly key: CryptoKey,
  ) {}

  private serializeMutation<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.mutationTail.then(operation);
    this.mutationTail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private async records(kind?: RecordKind, tripId?: string): Promise<EncryptedRecord[]> {
    return (await getAll<EncryptedRecord>(this.db, RECORDS)).filter(
      (record) =>
        record.ownerDriverId === this.driverId &&
        (kind === undefined || record.kind === kind) &&
        (tripId === undefined || record.tripId === tripId),
    );
  }

  private async metaOrDefault(tripId: string): Promise<TripMeta> {
    const stored = (await this.records("meta", tripId))[0];
    return stored
      ? decryptPayload<TripMeta>(this.key, stored)
      : { tripId, nextSeq: 0, batchesCut: 0, pingsRecorded: 0 };
  }

  addPing(tripId: string, ping: Omit<QueuedPing, "sequence_number">): Promise<QueuedPing> {
    return this.serializeMutation(() => this.addPingMutation(tripId, ping));
  }

  private async addPingMutation(
    tripId: string,
    ping: Omit<QueuedPing, "sequence_number">,
  ): Promise<QueuedPing> {
    const meta = await this.metaOrDefault(tripId);
    const queued: QueuedPing = { ...ping, sequence_number: meta.nextSeq };
    const nextMeta = {
      ...meta,
      nextSeq: meta.nextSeq + 1,
      pingsRecorded: meta.pingsRecorded + 1,
    };
    const pendingKey = recordKey(
      this.driverId,
      "pending",
      `${tripId}:${String(queued.sequence_number).padStart(16, "0")}`,
    );
    const metaKey = recordKey(this.driverId, "meta", tripId);
    const [pendingRecord, metaRecord] = await Promise.all([
      encryptPayload(
        this.key,
        { storageKey: pendingKey, ownerDriverId: this.driverId, tripId, kind: "pending" },
        queued,
      ),
      encryptPayload(
        this.key,
        { storageKey: metaKey, ownerDriverId: this.driverId, tripId, kind: "meta" },
        nextMeta,
      ),
    ]);
    const tx = this.db.transaction(RECORDS, "readwrite");
    tx.objectStore(RECORDS).put(pendingRecord);
    tx.objectStore(RECORDS).put(metaRecord);
    await transactionDone(tx);
    return queued;
  }

  cutBatch(tripId: string, max = 40): Promise<QueuedBatch | null> {
    return this.serializeMutation(() => this.cutBatchMutation(tripId, max));
  }

  private async cutBatchMutation(tripId: string, max: number): Promise<QueuedBatch | null> {
    const pendingRecords = (await this.records("pending", tripId)).sort((a, b) =>
      a.storageKey.localeCompare(b.storageKey),
    );
    const selected = pendingRecords.slice(0, max);
    if (selected.length === 0) return null;
    const pings = await Promise.all(
      selected.map((record) => decryptPayload<QueuedPing>(this.key, record)),
    );
    pings.sort((a, b) => a.sequence_number - b.sequence_number);
    const meta = await this.metaOrDefault(tripId);
    const batch: QueuedBatch = {
      key: crypto.randomUUID(),
      tripId,
      cutSeq: meta.batchesCut,
      cutAt: Date.now(),
      attempts: 0,
      pings,
    };
    const nextMeta = { ...meta, batchesCut: meta.batchesCut + 1 };
    const batchKey = recordKey(this.driverId, "batch", batch.key);
    const metaKey = recordKey(this.driverId, "meta", tripId);
    const [batchRecord, metaRecord] = await Promise.all([
      encryptPayload(
        this.key,
        { storageKey: batchKey, ownerDriverId: this.driverId, tripId, kind: "batch" },
        batch,
      ),
      encryptPayload(
        this.key,
        { storageKey: metaKey, ownerDriverId: this.driverId, tripId, kind: "meta" },
        nextMeta,
      ),
    ]);
    const tx = this.db.transaction(RECORDS, "readwrite");
    const store = tx.objectStore(RECORDS);
    store.put(batchRecord);
    store.put(metaRecord);
    for (const record of selected) store.delete(record.storageKey);
    await transactionDone(tx);
    return batch;
  }

  async listBatches(tripId?: string): Promise<QueuedBatch[]> {
    const rows = await this.records("batch", tripId);
    const batches = await Promise.all(
      rows.map((record) => decryptPayload<QueuedBatch>(this.key, record)),
    );
    return batches.sort(
      (a, b) => a.tripId.localeCompare(b.tripId) || a.cutSeq - b.cutSeq || a.cutAt - b.cutAt,
    );
  }

  async ackBatch(key: string): Promise<void> {
    const tx = this.db.transaction(RECORDS, "readwrite");
    tx.objectStore(RECORDS).delete(recordKey(this.driverId, "batch", key));
    await transactionDone(tx);
  }

  async dropBatch(key: string, diagnostic: { status?: number; code?: string } = {}): Promise<void> {
    const storageKey = recordKey(this.driverId, "batch", key);
    const tx = this.db.transaction([RECORDS, DEAD_LETTERS], "readwrite");
    const source = (await promisify(tx.objectStore(RECORDS).get(storageKey))) as
      EncryptedRecord | undefined;
    if (source) {
      tx.objectStore(DEAD_LETTERS).put({
        ...source,
        terminalStatus: diagnostic.status,
        terminalCode: diagnostic.code,
        rejectedAt: Date.now(),
      });
      tx.objectStore(RECORDS).delete(storageKey);
    }
    await transactionDone(tx);
  }

  async listDeadLetters(tripId?: string): Promise<DeadLetter[]> {
    const rows = (
      await getAll<
        EncryptedRecord & {
          terminalStatus?: number;
          terminalCode?: string;
          rejectedAt?: number;
        }
      >(this.db, DEAD_LETTERS)
    ).filter(
      (record) =>
        record.ownerDriverId === this.driverId &&
        (tripId === undefined || record.tripId === tripId),
    );
    return Promise.all(
      rows.map(async (record) => ({
        ...(await decryptPayload<QueuedBatch>(this.key, record)),
        terminalStatus: record.terminalStatus,
        terminalCode: record.terminalCode,
        rejectedAt: record.rejectedAt,
      })),
    );
  }

  async deadLetterCount(tripId: string): Promise<number> {
    return (await this.listDeadLetters(tripId)).length;
  }

  async recordAttempt(key: string): Promise<void> {
    const storageKey = recordKey(this.driverId, "batch", key);
    const source = (await this.records("batch")).find((record) => record.storageKey === storageKey);
    if (!source) return;
    const batch = await decryptPayload<QueuedBatch>(this.key, source);
    const updated = await encryptPayload(this.key, source, {
      ...batch,
      attempts: batch.attempts + 1,
    });
    const tx = this.db.transaction(RECORDS, "readwrite");
    tx.objectStore(RECORDS).put(updated);
    await transactionDone(tx);
  }

  async pendingCount(tripId: string): Promise<number> {
    return (await this.records("pending", tripId)).length;
  }

  async unsyncedCount(tripId: string): Promise<number> {
    const pending = await this.pendingCount(tripId);
    const batches = await this.listBatches(tripId);
    return pending + batches.reduce((sum, batch) => sum + batch.pings.length, 0);
  }

  meta(tripId: string): Promise<TripMeta> {
    return this.metaOrDefault(tripId);
  }

  async tripsWithLeftovers(): Promise<string[]> {
    const rows = await this.records();
    return [...new Set(rows.filter((row) => row.kind !== "meta").map((row) => row.tripId))];
  }

  async forgetTrip(tripId: string): Promise<void> {
    const rows = await this.records(undefined, tripId);
    const tx = this.db.transaction(RECORDS, "readwrite");
    for (const row of rows) tx.objectStore(RECORDS).delete(row.storageKey);
    await transactionDone(tx);
  }

  close(): void {
    this.db.close();
  }
}

export async function openPingQueue(options?: string | OpenPingQueueOptions): Promise<PingQueue> {
  const normalized: Required<
    Pick<OpenPingQueueOptions, "driverId" | "dbName" | "requireMigrationLock">
  > &
    Pick<OpenPingQueueOptions, "verifyTripOwner"> =
    typeof options === "string" || options === undefined
      ? {
          driverId: "__isolated_capability_probe__",
          dbName: options ?? DEFAULT_DB_NAME,
          requireMigrationLock: false,
          verifyTripOwner: undefined,
        }
      : {
          driverId: options.driverId,
          dbName: options.dbName ?? DEFAULT_DB_NAME,
          requireMigrationLock: options.requireMigrationLock ?? true,
          verifyTripOwner: options.verifyTripOwner,
        };
  if (!normalized.driverId) throw new Error("A server-verified driver identity is required");
  return withMigrationLock(normalized.requireMigrationLock, async () => {
    const db = await openDatabase(normalized.dbName);
    try {
      const key = await loadOrCreateDriverKey(db, normalized.driverId);
      await migrateLegacy(db, normalized.driverId, key, normalized.verifyTripOwner);
      return new PingQueue(db, normalized.driverId, key);
    } catch (error) {
      db.close();
      throw error;
    }
  });
}
