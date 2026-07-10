"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import type { components } from "@/lib/api/schema";

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
  action: z.enum(["accept", "activate", "deactivate"]),
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
    } else if (action === "activate") {
      await api.POST("/api/v1/driver/campaign-assignments/{assignment_id}/activate", request);
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
  trip?: components["schemas"]["TripRead"];
}

export async function startTripAction(assignmentId: string): Promise<StartTripResult> {
  if (!z.string().uuid().safeParse(assignmentId).success) {
    return { error: "Invalid assignment" };
  }
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/start", {
      body: { assignment_id: assignmentId },
    });
    revalidateDriver();
    return { trip: data };
  } catch (error) {
    return toState(error);
  }
}

export async function endTripAction(tripId: string): Promise<DriverActionState> {
  if (!z.string().uuid().safeParse(tripId).success) return { error: "Invalid trip" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/driver/trips/{trip_id}/end", {
      params: { path: { trip_id: tripId } },
      body: { end_reason: "driver_ended" },
    });
  } catch (error) {
    return toState(error);
  }
  revalidateDriver();
  return {};
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
  pings: z.array(pingSchema).min(1).max(200),
});

export interface PingBatchResult extends DriverActionState {
  acceptedCount?: number;
  duplicate?: boolean;
}

export async function sendPingBatchAction(
  input: z.input<typeof pingBatchSchema>,
): Promise<PingBatchResult> {
  const parsed = pingBatchSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid ping batch" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/driver/trips/{trip_id}/pings", {
      params: { path: { trip_id: parsed.data.tripId } },
      body: {
        idempotency_key: parsed.data.idempotencyKey,
        pings: parsed.data.pings,
      },
    });
    return { acceptedCount: data?.accepted_count, duplicate: data?.duplicate };
  } catch (error) {
    return toState(error);
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
