import { describe, expect, it } from "vitest";
import vectors from "./trip-evidence-v2-vectors.json";
import { batchPayloadHash, buildEvidenceManifest, canonicalBytes } from "./trip-evidence";

describe("trip evidence v2 canonical contract", () => {
  it("matches the shared Python/TypeScript batch and manifest vectors", async () => {
    const payloadHash = await batchPayloadHash(vectors.batch.pings);
    expect(payloadHash).toBe(vectors.batch.payload_hash);
    const manifest = await buildEvidenceManifest(
      vectors.trip_id,
      [
        {
          batch_sequence: vectors.batch.batch_sequence,
          idempotency_key: vectors.batch.idempotency_key,
          payload_hash_version: 2,
          payload_hash: payloadHash,
          submitted_count: vectors.batch.pings.length,
        },
      ],
      true,
    );
    expect(manifest.root_sha256).toBe(vectors.manifest_root);
  });

  it("sorts object keys by UTF-8 bytes and rejects non-finite values", () => {
    expect(canonicalBytes({ b: 1, a: 2 })).toEqual(canonicalBytes({ a: 2, b: 1 }));
    expect(() => canonicalBytes(Number.NaN)).toThrow(/finite/);
  });

  it("rejects non-millisecond evidence timestamps", async () => {
    const ping = vectors.batch.pings[0]!;
    await expect(
      batchPayloadHash([{ ...ping, recorded_at: "2026-09-01T11:34:56.789123Z" }]),
    ).rejects.toThrow(/millisecond/);
  });
});
