"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import type { EvidenceReceipt, TripOwnershipVerification } from "@/lib/trips/ping-queue";
import type { EvidenceManifest } from "@/lib/trips/trip-evidence";

export interface DriverActionState {
  error?: string;
}

function toState(error: unknown): DriverActionState {
  if (error instanceof ApiError) return { error: error.message };
  return { error: "Could not reach the server. Please try again." };
}

function revalidateDriver() {
  revalidatePath("/driver");
  revalidatePath("/driver/assignments");
  revalidatePath("/driver/track");
}

// --- assignments -----------------------------------------------------------

const assignmentSchema = z.object({
  assignmentId: z.string().uuid(),
  action: z.enum(["accept", "deactivate"]),
});

export async function assignmentAction(
  input: z.input<typeof assignmentSchema>,
): Promise<DriverActionState> {
  const parsed = assignmentSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid assignment action" };
  const { assignmentId, action } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    const request = { params: { path: { assignment_id: assignmentId } }, body: {} };
    if (action === "accept") {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/accept", request);
    } else {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/deactivate", request);
    }
  } catch (error) {
    return toState(error);
  }
  revalidateDriver();
  return {};
}

// --- trips -------------------------------------------------------------------

export interface StartTripResult extends DriverActionState {
  trip?: { id: string; evidenceProtocolVersion: 1 | 2 };
  outcome?: "started" | "failed" | "unknown";
}

export async function startTripAction(assignmentId: string): Promise<StartTripResult> {
  if (!z.string().uuid().safeParse(assignmentId).success) {
    return { error: "Invalid assignment", outcome: "failed" };
  }
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/start", {
      body: { assignment_id: assignmentId, evidence_protocol_version: 2 },
    });
    revalidateDriver();
    return {
      trip: data
        ? { id: data.id, evidenceProtocolVersion: data.evidence_protocol_version as 1 | 2 }
        : undefined,
      outcome: data ? "started" : "unknown",
    };
  } catch (error) {
    if (error instanceof ApiError && [400, 403, 404, 422].includes(error.status)) {
      return { error: error.message, outcome: "failed" };
    }
    return { ...toState(error), outcome: "unknown" };
  }
}

export async function getCurrentTripAction(): Promise<StartTripResult> {
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/current");
    return {
      trip: data?.trip
        ? {
            id: data.trip.id,
            evidenceProtocolVersion: data.trip.evidence_protocol_version as 1 | 2,
          }
        : undefined,
      outcome: data?.trip ? "started" : "failed",
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { outcome: "failed" };
    return { ...toState(error), outcome: "unknown" };
  }
}

export async function verifyDriverTripOwnershipAction(
  tripId: string,
): Promise<TripOwnershipVerification> {
  if (!z.string().uuid().safeParse(tripId).success) return "unavailable";
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/{trip_id}", {
      params: { path: { trip_id: tripId } },
    });
    return data?.id === tripId ? "owned" : "unavailable";
  } catch (error) {
    return error instanceof ApiError && error.status === 404 && error.code === "TRIP_NOT_FOUND"
      ? "not-owned"
      : "unavailable";
  }
}

export async function getTripEvidenceAuthorityAction(
  tripId: string,
): Promise<{ protocolVersion: 1 | 2; status: "active" | "ended" | "sealed" } | undefined> {
  if (!z.string().uuid().safeParse(tripId).success) return undefined;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/{trip_id}", {
      params: { path: { trip_id: tripId } },
    });
    return data?.id === tripId
      ? {
          protocolVersion: data.evidence_protocol_version as 1 | 2,
          status: data.status,
        }
      : undefined;
  } catch {
    return undefined;
  }
}

const manifestEntrySchema = z.object({
  batch_sequence: z.number().int().nonnegative(),
  idempotency_key: z.string().min(1),
  payload_hash_version: z.literal(2),
  payload_hash: z.string().regex(/^[0-9a-f]{64}$/),
  submitted_count: z.number().int().nonnegative(),
});

const evidenceManifestSchema = z.object({
  version: z.literal(2),
  root_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  ping_count: z.number().int().nonnegative(),
  complete: z.boolean(),
  entries: z.array(manifestEntrySchema),
});

export interface EndTripResult extends DriverActionState {
  outcome: "ended" | "failed" | "unknown";
  status?: "ended" | "sealed";
}

export async function endTripAction(
  tripId: string,
  evidenceManifest: EvidenceManifest,
): Promise<EndTripResult> {
  if (!z.string().uuid().safeParse(tripId).success)
    return { error: "Invalid trip", outcome: "failed" };
  const parsedManifest = evidenceManifestSchema.safeParse(evidenceManifest);
  if (!parsedManifest.success) return { error: "Invalid trip end state", outcome: "failed" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/{trip_id}/end", {
      params: { path: { trip_id: tripId } },
      body: {
        end_reason: "driver_ended",
        evidence_manifest: parsedManifest.data,
      },
    });
    const returnedStatus = data?.status;
    if (
      !data ||
      data.id !== tripId ||
      (returnedStatus !== "ended" && returnedStatus !== "sealed")
    ) {
      return {
        error: "Cardvert could not confirm whether the trip ended.",
        outcome: "unknown",
      };
    }
    revalidateDriver();
    return { outcome: "ended", status: returnedStatus };
  } catch (error) {
    const outcome =
      error instanceof ApiError && [400, 403, 404, 422].includes(error.status)
        ? "failed"
        : "unknown";
    return { ...toState(error), outcome };
  }
}

export async function endLegacyTripAction(
  tripId: string,
  watermark: { clientBatchCount: number; clientPingCount: number; clientComplete: boolean },
): Promise<EndTripResult> {
  if (!z.string().uuid().safeParse(tripId).success)
    return { error: "Invalid trip", outcome: "failed" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/{trip_id}/end", {
      params: { path: { trip_id: tripId } },
      body: {
        end_reason: "driver_ended",
        client_batch_count: watermark.clientBatchCount,
        client_ping_count: watermark.clientPingCount,
        client_complete: watermark.clientComplete,
      },
    });
    const returnedStatus = data?.status;
    return !data ||
      data.id !== tripId ||
      (returnedStatus !== "ended" && returnedStatus !== "sealed")
      ? { error: "Trip end was not confirmed.", outcome: "unknown" }
      : { outcome: "ended", status: returnedStatus };
  } catch (error) {
    const outcome =
      error instanceof ApiError && [400, 403, 404, 409, 422].includes(error.status)
        ? "failed"
        : "unknown";
    return { ...toState(error), outcome };
  }
}

const pingSchema = z.object({
  recorded_at: z.string(),
  lat: z.number().min(-90).max(90),
  lon: z.number().min(-180).max(180),
  accuracy_m: z.number().nonnegative().nullable(),
  speed_mps: z.number().nonnegative().nullable(),
  heading_degrees: z.number().min(0).max(360).nullable(),
  sequence_number: z.number().int().nonnegative(),
});

const pingBatchSchema = z.object({
  tripId: z.string().uuid(),
  idempotencyKey: z.string().min(8).max(128),
  batchSequence: z.number().int().nonnegative(),
  evidenceProtocolVersion: z.union([z.literal(1), z.literal(2)]),
  pings: z.array(pingSchema).min(1).max(200),
});

const legacyPingBatchAckSchema = z.object({
  batch_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  accepted_count: z.number().int().nonnegative(),
  submitted_count: z.number().int().nonnegative(),
  rejected_count: z.number().int().nonnegative(),
  duplicate: z.boolean(),
  quarantined: z.boolean(),
});

const pingBatchAckSchema = legacyPingBatchAckSchema.extend({
  batch_sequence: z.number().int().nonnegative(),
  payload_hash_version: z.literal(2),
  payload_hash: z.string().regex(/^[0-9a-f]{64}$/),
  outcome: z.string(),
  receipt_format_version: z.number().int().positive(),
  receipt_key_version: z.number().int().positive(),
  receipt_signature: z.string().min(1),
});

export interface PingBatchResult extends DriverActionState {
  /** True only when the backend returned its complete D15/D16 ACK envelope. */
  acknowledged: boolean;
  acceptedCount?: number;
  duplicate?: boolean;
  /** Trip already sealed: server preserved the batch as quarantine evidence. */
  quarantined?: boolean;
  receipt?: EvidenceReceipt;
  /**
   * When `error` is set: whether retrying the same batch can ever succeed.
   * Validation/conflict rejections (400/409/422) are terminal — the client
   * must drop the batch instead of head-of-line-blocking its queue forever.
   */
  retryable?: boolean;
  terminalStatus?: number;
  terminalCode?: string;
}

export async function sendPingBatchAction(
  input: z.input<typeof pingBatchSchema>,
): Promise<PingBatchResult> {
  const parsed = pingBatchSchema.safeParse(input);
  if (!parsed.success)
    return { error: "Invalid ping batch", retryable: false, acknowledged: false };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/{trip_id}/pings", {
      params: { path: { trip_id: parsed.data.tripId } },
      body: {
        idempotency_key: parsed.data.idempotencyKey,
        batch_sequence: parsed.data.batchSequence,
        pings: parsed.data.pings,
      },
    });
    if (parsed.data.evidenceProtocolVersion === 1) {
      const acknowledgement = legacyPingBatchAckSchema.safeParse(data);
      const positiveAck =
        acknowledgement.success &&
        acknowledgement.data.trip_id === parsed.data.tripId &&
        acknowledgement.data.submitted_count === parsed.data.pings.length &&
        (acknowledgement.data.duplicate ||
          acknowledgement.data.quarantined ||
          acknowledgement.data.accepted_count === parsed.data.pings.length);
      if (!positiveAck)
        return { error: "GPS batch was not confirmed.", retryable: true, acknowledged: false };
      return {
        acknowledged: true,
        acceptedCount: acknowledgement.data.accepted_count,
        duplicate: acknowledgement.data.duplicate,
        quarantined: acknowledgement.data.quarantined,
      };
    }
    const acknowledgement = pingBatchAckSchema.safeParse(data);
    const positiveAck =
      acknowledgement.success &&
      acknowledgement.data.trip_id === parsed.data.tripId &&
      (acknowledgement.data.duplicate ||
        acknowledgement.data.quarantined ||
        acknowledgement.data.accepted_count === parsed.data.pings.length);
    if (!positiveAck) {
      return {
        error: "Cardvert could not confirm the GPS batch acknowledgement.",
        retryable: true,
        acknowledged: false,
      };
    }
    return {
      acknowledged: true,
      acceptedCount: acknowledgement.data.accepted_count,
      duplicate: acknowledgement.data.duplicate,
      quarantined: acknowledgement.data.quarantined,
      receipt: {
        tripId: acknowledgement.data.trip_id,
        batchId: acknowledgement.data.batch_id,
        batch_sequence: acknowledgement.data.batch_sequence,
        idempotency_key: parsed.data.idempotencyKey,
        payload_hash_version: acknowledgement.data.payload_hash_version,
        payload_hash: acknowledgement.data.payload_hash,
        submitted_count: acknowledgement.data.submitted_count,
        acceptedCount: acknowledgement.data.accepted_count,
        rejectedCount: acknowledgement.data.rejected_count,
        outcome: acknowledgement.data.outcome,
        receiptFormatVersion: acknowledgement.data.receipt_format_version,
        receiptKeyVersion: acknowledgement.data.receipt_key_version,
        receiptSignature: acknowledgement.data.receipt_signature,
      },
    };
  } catch (error) {
    if (error instanceof ApiError) {
      const terminal = [400, 409, 422].includes(error.status);
      return {
        error: error.message,
        acknowledged: false,
        retryable: !terminal,
        terminalStatus: terminal ? error.status : undefined,
        terminalCode: terminal ? error.code : undefined,
      };
    }
    return { ...toState(error), acknowledged: false, retryable: true };
  }
}

export async function reconcileTripEvidenceAction(tripId: string): Promise<EndTripResult> {
  if (!z.string().uuid().safeParse(tripId).success)
    return { error: "Invalid trip", outcome: "failed" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/{trip_id}/evidence/reconcile", {
      params: { path: { trip_id: tripId } },
    });
    return data?.status === "sealed"
      ? { outcome: "ended", status: "sealed" }
      : { error: "Trip evidence is not sealed.", outcome: "unknown" };
  } catch (error) {
    const outcome =
      error instanceof ApiError && [400, 403, 404, 409, 422].includes(error.status)
        ? "failed"
        : "unknown";
    return { ...toState(error), outcome };
  }
}

// --- profile -----------------------------------------------------------------

const profileSchema = z.object({
  license_number: z
    .string()
    .trim()
    .max(64)
    .transform((v) => (v === "" ? null : v)),
  service_city: z
    .string()
    .trim()
    .max(120)
    .transform((v) => (v === "" ? null : v)),
  country_code: z
    .string()
    .trim()
    .toUpperCase()
    .transform((v) => (v === "" ? null : v))
    .pipe(z.string().length(2, "Use a 2-letter code (e.g. NG)").nullable()),
});

export async function updateProfileAction(
  _prev: DriverActionState,
  formData: FormData,
): Promise<DriverActionState> {
  const parsed = profileSchema.safeParse({
    license_number: formData.get("license_number") ?? "",
    service_city: formData.get("service_city") ?? "",
    country_code: formData.get("country_code") ?? "",
  });
  if (!parsed.success) {
    return { error: parsed.error.issues[0]?.message ?? "Invalid profile data" };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/driver/profile", { body: parsed.data });
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/driver/profile");
  return {};
}
