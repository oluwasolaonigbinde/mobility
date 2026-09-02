const encoder = new TextEncoder();

export const EVIDENCE_PROTOCOL_VERSION = 2 as const;
export const PAYLOAD_HASH_VERSION = 2 as const;
const BATCH_DOMAIN = encoder.encode("cardvert.trip-batch.v2\0");
const MANIFEST_ENTRY_DOMAIN = encoder.encode("cardvert.trip-manifest-entry.v2\0");
const MANIFEST_DOMAIN = encoder.encode("cardvert.trip-manifest.v2\0");

type CanonicalValue =
  | null
  | boolean
  | number
  | string
  | CanonicalFloat
  | CanonicalValue[]
  | { [key: string]: CanonicalValue };

class CanonicalFloat {
  constructor(readonly value: number) {}
}

function float64(value: number | null): CanonicalFloat | null {
  return value === null ? null : new CanonicalFloat(value);
}

function concat(...parts: Uint8Array<ArrayBufferLike>[]): Uint8Array<ArrayBuffer> {
  const result = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function u32(value: number): Uint8Array {
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff)
    throw new Error("canonical u32 is out of range");
  const result = new Uint8Array(4);
  new DataView(result.buffer).setUint32(0, value, false);
  return result;
}

function i64(value: number): Uint8Array {
  if (!Number.isSafeInteger(value)) throw new Error("canonical i64 is out of range");
  const result = new Uint8Array(8);
  new DataView(result.buffer).setBigInt64(0, BigInt(value), false);
  return result;
}

function binary64(value: number): Uint8Array {
  if (!Number.isFinite(value)) throw new Error("canonical floats must be finite");
  const result = new Uint8Array(8);
  new DataView(result.buffer).setFloat64(0, Object.is(value, -0) ? 0 : value, false);
  return result;
}

function compareBytes(left: Uint8Array, right: Uint8Array): number {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left[index] !== right[index]) return (left[index] ?? 0) - (right[index] ?? 0);
  }
  return left.length - right.length;
}

export function canonicalBytes(value: CanonicalValue): Uint8Array {
  if (value === null) return encoder.encode("n");
  if (value === false) return encoder.encode("f");
  if (value === true) return encoder.encode("t");
  if (value instanceof CanonicalFloat) return concat(encoder.encode("d"), binary64(value.value));
  if (typeof value === "number")
    return Number.isInteger(value)
      ? concat(encoder.encode("i"), i64(value))
      : concat(encoder.encode("d"), binary64(value));
  if (typeof value === "string") {
    const encoded = encoder.encode(value);
    return concat(encoder.encode("s"), u32(encoded.length), encoded);
  }
  if (Array.isArray(value))
    return concat(
      encoder.encode("a"),
      u32(value.length),
      ...value.map((item) => canonicalBytes(item)),
    );
  const entries = Object.entries(value).sort(([left], [right]) =>
    compareBytes(encoder.encode(left), encoder.encode(right)),
  );
  return concat(
    encoder.encode("o"),
    u32(entries.length),
    ...entries.flatMap(([key, item]) => [canonicalBytes(key), canonicalBytes(item)]),
  );
}

async function sha256(...parts: Uint8Array<ArrayBufferLike>[]): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", concat(...parts));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export interface EvidencePing {
  recorded_at: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  speed_mps: number | null;
  heading_degrees: number | null;
  sequence_number: number;
}

function epochMilliseconds(value: string): number {
  if (!/\.\d{3}(?:Z|[+-]\d{2}:\d{2})$/.test(value))
    throw new Error("evidence timestamp must have exact millisecond precision");
  const milliseconds = Date.parse(value);
  if (!Number.isSafeInteger(milliseconds)) throw new Error("invalid evidence timestamp");
  const canonical = new Date(milliseconds).toISOString();
  if (!canonical.endsWith("Z"))
    throw new Error("evidence timestamp must resolve to UTC milliseconds");
  return milliseconds;
}

export async function batchPayloadHash(pings: EvidencePing[]): Promise<string> {
  const value: CanonicalValue = {
    pings: pings.map((ping) => ({
      recorded_at_ms: epochMilliseconds(ping.recorded_at),
      lat: float64(ping.lat),
      lon: float64(ping.lon),
      accuracy_m: float64(ping.accuracy_m),
      speed_mps: float64(ping.speed_mps),
      heading_degrees: float64(ping.heading_degrees),
      altitude_m: null,
      sequence_number: ping.sequence_number,
      metadata: {},
    })),
    metadata: {},
  };
  return sha256(BATCH_DOMAIN, canonicalBytes(value));
}

export interface EvidenceManifestEntry {
  batch_sequence: number;
  idempotency_key: string;
  payload_hash_version: 2;
  payload_hash: string;
  submitted_count: number;
}

function entryValue(entry: EvidenceManifestEntry): CanonicalValue {
  return {
    batch_sequence: entry.batch_sequence,
    idempotency_key: entry.idempotency_key,
    payload_hash_version: entry.payload_hash_version,
    payload_hash: entry.payload_hash,
    submitted_count: entry.submitted_count,
  };
}

export interface EvidenceManifest {
  version: 2;
  root_sha256: string;
  ping_count: number;
  complete: boolean;
  entries: EvidenceManifestEntry[];
}

export async function buildEvidenceManifest(
  tripId: string,
  entries: EvidenceManifestEntry[],
  complete: boolean,
): Promise<EvidenceManifest> {
  const ordered = [...entries].sort((left, right) => left.batch_sequence - right.batch_sequence);
  if (
    ordered.some((entry, index) => entry.batch_sequence !== index) ||
    new Set(ordered.map((entry) => entry.idempotency_key)).size !== ordered.length
  )
    throw new Error("evidence manifest entries must be unique, ordered, and contiguous");
  const entryDigests = await Promise.all(
    ordered.map((entry) => sha256(MANIFEST_ENTRY_DOMAIN, canonicalBytes(entryValue(entry)))),
  );
  const pingCount = ordered.reduce((sum, entry) => sum + entry.submitted_count, 0);
  const root = await sha256(
    MANIFEST_DOMAIN,
    canonicalBytes({
      version: EVIDENCE_PROTOCOL_VERSION,
      trip_id: tripId,
      batch_count: ordered.length,
      ping_count: pingCount,
      entry_digests: entryDigests,
    }),
  );
  return {
    version: EVIDENCE_PROTOCOL_VERSION,
    root_sha256: root,
    ping_count: pingCount,
    complete,
    entries: ordered,
  };
}
