"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
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
  if (error instanceof ApiError) return { error: publicActionError(error) };
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
    unstable_rethrow(error);
    return toState(error);
  }
  revalidateDriver();
  return {};
}

// --- trips -------------------------------------------------------------------

export interface StartTripResult extends DriverActionState {
  trip?: { id: string; startedAt?: string; evidenceProtocolVersion: 2 };
  outcome?: "started" | "failed" | "unknown";
}

/** Start refusals that mean the driver has a photo task to do first; never an uncertain start. */
const START_PHOTO_REFUSALS: Record<string, string> = {
  APPROVED_INSTALLATION_EVIDENCE_REQUIRED:
    "Your installation photos need to be approved first. Send them from Jobs.",
  INSTALLATION_EVIDENCE_EXPIRED: "New installation photos are due. Send them from Jobs.",
};

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
      trip:
        data?.evidence_protocol_version === 2
          ? {
              id: data.id,
              startedAt: data.started_at,
              evidenceProtocolVersion: data.evidence_protocol_version as 2,
            }
          : undefined,
      outcome: data?.evidence_protocol_version === 2 ? "started" : "unknown",
    };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && START_PHOTO_REFUSALS[error.code]) {
      return { error: START_PHOTO_REFUSALS[error.code], outcome: "failed" };
    }
    if (error instanceof ApiError && [400, 403, 404, 422].includes(error.status)) {
      return { error: publicActionError(error), outcome: "failed" };
    }
    return { ...toState(error), outcome: "unknown" };
  }
}

export async function getCurrentTripAction(): Promise<StartTripResult> {
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/current");
    return {
      trip:
        data?.trip?.evidence_protocol_version === 2
          ? {
              id: data.trip.id,
              startedAt: data.trip.started_at,
              evidenceProtocolVersion: data.trip.evidence_protocol_version as 2,
            }
          : undefined,
      outcome:
        data?.trip?.evidence_protocol_version === 2 ? "started" : data?.trip ? "unknown" : "failed",
    };
  } catch (error) {
    unstable_rethrow(error);
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
    unstable_rethrow(error);
    return error instanceof ApiError && error.status === 404 && error.code === "TRIP_NOT_FOUND"
      ? "not-owned"
      : "unavailable";
  }
}

export async function getTripEvidenceAuthorityAction(
  tripId: string,
): Promise<{ protocolVersion: 2; status: "active" | "ended" | "sealed" } | undefined> {
  if (!z.string().uuid().safeParse(tripId).success) return undefined;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/{trip_id}", {
      params: { path: { trip_id: tripId } },
    });
    return data?.id === tripId && data.evidence_protocol_version === 2
      ? {
          protocolVersion: data.evidence_protocol_version as 2,
          status: data.status,
        }
      : undefined;
  } catch (caught) {
    unstable_rethrow(caught);
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

/**
 * End refusals raised before the server writes anything: the manifest does
 * not match the evidence it holds (e.g. this device lost its local record).
 * The caller may rebuild the manifest from the server's receipts and retry.
 */
const MANIFEST_MISMATCH_CODES = new Set([
  "TRIP_EVIDENCE_MANIFEST_INVALID",
  "TRIP_EVIDENCE_MANIFEST_REQUIRED",
]);

export interface EndTripResult extends DriverActionState {
  /** `evidence_mismatch`: refused before any write; rebuild the manifest and retry. */
  outcome: "ended" | "failed" | "unknown" | "evidence_mismatch";
  status?: "ended" | "sealed";
  /**
   * Set when the server finally adjudicated a trip whose declared evidence can
   * no longer arrive. The trip is not sealed and no money is opened, but the
   * disposition is terminal and server-authorized (OFF-006).
   */
  adjudication?: "incomplete_grace_expired";
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
    unstable_rethrow(error);
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      MANIFEST_MISMATCH_CODES.has(error.code ?? "")
    )
      return { ...toState(error), outcome: "evidence_mismatch" };
    const outcome =
      error instanceof ApiError && [400, 403, 404, 422].includes(error.status)
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
  heading_degrees: z.number().min(0).lt(360).nullable(),
  sequence_number: z.number().int().nonnegative(),
});

const pingBatchSchema = z.object({
  tripId: z.string().uuid(),
  idempotencyKey: z.string().min(8).max(128),
  batchSequence: z.number().int().nonnegative(),
  evidenceProtocolVersion: z.literal(2),
  pings: z.array(pingSchema).min(1).max(200),
});

const basePingBatchAckSchema = z.object({
  batch_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  accepted_count: z.number().int().nonnegative(),
  submitted_count: z.number().int().nonnegative(),
  rejected_count: z.number().int().nonnegative(),
  duplicate: z.boolean(),
  evidence_scope: z.enum(["manifest", "late", "late_dropped"]),
});

const sampleResultSchema = z.object({
  index: z.number().int().nonnegative(),
  sequence_number: z.number().int().nonnegative().nullable(),
  status: z.enum(["accepted", "rejected"]),
  rejection_code: z
    .enum([
      "INVALID_RECORDED_AT",
      "INVALID_ASSIGNMENT_AUTHORITY",
      "INVALID_ACCURACY",
      "INVALID_SPEED",
      "PAY_ALREADY_CALCULATED",
    ])
    .nullable(),
});

const pingBatchAckSchema = basePingBatchAckSchema.extend({
  batch_sequence: z.number().int().nonnegative(),
  payload_hash_version: z.literal(2),
  payload_hash: z.string().regex(/^[0-9a-f]{64}$/),
  outcome: z.enum(["accepted", "dropped"]),
  receipt_format_version: z.number().int().positive(),
  receipt_key_version: z.number().int().positive(),
  receipt_signature: z.string().min(1),
  sample_results: z.array(sampleResultSchema).default([]),
});

/**
 * Rejections the ended-policy authority may still accept. Evidence already
 * captured under a since-deactivated assignment is refused while the trip is
 * active, but the exact same batch lands once End commits its manifest — so
 * dead-lettering it here would destroy valid evidence the server would take.
 */
const DEFERRABLE_REJECTION_CODES = new Set(["CAMPAIGN_ASSIGNMENT_NOT_ACTIVE"]);
const SEQUENCE_TAKEN_CODE = "TRIP_EVIDENCE_BATCH_SEQUENCE_TAKEN";

function receiptFromAck(
  ack: z.infer<typeof pingBatchAckSchema>,
  idempotencyKey: string,
): EvidenceReceipt {
  return {
    tripId: ack.trip_id,
    batchId: ack.batch_id,
    batch_sequence: ack.batch_sequence,
    idempotency_key: idempotencyKey,
    payload_hash_version: ack.payload_hash_version,
    payload_hash: ack.payload_hash,
    submitted_count: ack.submitted_count,
    acceptedCount: ack.accepted_count,
    rejectedCount: ack.rejected_count,
    outcome: ack.outcome,
    evidenceScope: ack.evidence_scope,
    receiptFormatVersion: ack.receipt_format_version,
    receiptKeyVersion: ack.receipt_key_version,
    receiptSignature: ack.receipt_signature,
    sampleResults: ack.sample_results,
  };
}

const serverEvidenceSchema = z.object({
  trip_id: z.string().uuid(),
  batches: z.array(pingBatchAckSchema.extend({ idempotency_key: z.string().min(1) })),
});

/**
 * The signed receipts the server holds for this driver's trip. A device with
 * no local record of the trip adopts them so it can continue numbering and
 * declare them when it ends the trip. Undefined when they can't be read.
 */
export async function getTripEvidenceAction(
  tripId: string,
): Promise<EvidenceReceipt[] | undefined> {
  if (!z.string().uuid().safeParse(tripId).success) return undefined;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/driver/trips/{trip_id}/evidence", {
      params: { path: { trip_id: tripId } },
    });
    const parsed = serverEvidenceSchema.safeParse(data);
    if (!parsed.success || parsed.data.trip_id !== tripId) return undefined;
    if (
      parsed.data.batches.some(
        (batch) =>
          batch.trip_id !== tripId ||
          batch.accepted_count + batch.rejected_count !== batch.submitted_count ||
          (batch.rejected_count > 0 && batch.sample_results.length !== batch.submitted_count),
      )
    )
      return undefined;
    return parsed.data.batches.map((batch) => receiptFromAck(batch, batch.idempotency_key));
  } catch (error) {
    unstable_rethrow(error);
    return undefined;
  }
}

export interface PingBatchResult extends DriverActionState {
  /** True only when the backend returned its complete D15/D16 ACK envelope. */
  acknowledged: boolean;
  acceptedCount?: number;
  duplicate?: boolean;
  receipt?: EvidenceReceipt;
  /**
   * When `error` is set: whether retrying the same batch can ever succeed.
   * Validation/conflict rejections (400/409/422) are terminal — the client
   * must drop the batch instead of head-of-line-blocking its queue forever.
   */
  retryable?: boolean;
  /**
   * True when the rejection is retryable only because a later lifecycle step
   * (ending the trip) can still accept this exact batch. The caller must keep
   * the batch queued and must not dead-letter it (OFF-006).
   */
  deferred?: boolean;
  terminalStatus?: number;
  terminalCode?: string;
  /** The server already holds this batch number: resync, renumber, resend. */
  sequenceTaken?: boolean;
  /** Per-sample disposition of a durably acknowledged batch (OFF-005). */
  sampleResults?: Array<{
    index: number;
    sequence_number: number | null;
    status: "accepted" | "rejected";
    rejection_code: string | null;
  }>;
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
    const acknowledgement = pingBatchAckSchema.safeParse(data);
    const positiveAck =
      acknowledgement.success &&
      acknowledgement.data.trip_id === parsed.data.tripId &&
      acknowledgement.data.accepted_count + acknowledgement.data.rejected_count ===
        acknowledgement.data.submitted_count &&
      (acknowledgement.data.duplicate ||
        // A partially accepted batch is still durably settled: the server
        // adjudicated every sample and signed the disposition, so resending
        // it would only replay the same answer (OFF-005).
        (acknowledgement.data.submitted_count === parsed.data.pings.length &&
          acknowledgement.data.sample_results.length === parsed.data.pings.length));
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
      sampleResults: acknowledgement.data.sample_results,
      receipt: receiptFromAck(acknowledgement.data, parsed.data.idempotencyKey),
    };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && error.code === SEQUENCE_TAKEN_CODE) {
      // This device's batch number is already used on the server (it lost
      // its local record). Not terminal: resync and renumber, then resend.
      return {
        error: publicActionError(error),
        acknowledged: false,
        retryable: true,
        sequenceTaken: true,
      };
    }
    if (error instanceof ApiError) {
      const deferred = DEFERRABLE_REJECTION_CODES.has(error.code ?? "");
      const terminal = !deferred && [400, 409, 422].includes(error.status);
      return {
        error: publicActionError(error),
        acknowledged: false,
        retryable: !terminal,
        deferred,
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
    if (data?.status === "sealed") return { outcome: "ended", status: "sealed" };
    if (data?.adjudication_outcome === "incomplete_grace_expired" && data.receipt_signature) {
      return {
        outcome: "ended",
        status: "ended",
        adjudication: "incomplete_grace_expired",
      };
    }
    return { error: "Trip evidence is not sealed.", outcome: "unknown" };
  } catch (error) {
    unstable_rethrow(error);
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "TRIP_EVIDENCE_INCOMPLETE"
    ) {
      // The server's recovery window is still open. This is neither success
      // nor a terminal refusal: recovery must retry until the server verifies
      // the manifest or signs its final incomplete adjudication (OFF-006).
      return { ...toState(error), outcome: "unknown" };
    }
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
  service_city: z.string().trim().min(1, "Enter the city you drive in").max(128),
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
    unstable_rethrow(error);
    return toState(error);
  }
  revalidatePath("/driver/profile");
  return {};
}
