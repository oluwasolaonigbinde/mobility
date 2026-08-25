"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface AdminActionState {
  error?: string;
}

export interface AssignmentRecommendation {
  rank: number;
  driver_profile_id: string;
  driver_name: string;
  vehicle_id: string;
  vehicle_plate_number: string;
  vehicle_make: string | null;
  vehicle_model: string | null;
  service_city: string;
  vehicle_type: "car";
  matching_version: "matching_v1";
  fingerprint: string;
  components: {
    vehicle_load: number;
    driver_load: number;
    active_tracking_seconds: number;
    latest_computed_at: string | null;
  };
}

export interface AssignmentRecommendationActionState {
  error?: string;
  candidates?: AssignmentRecommendation[];
}

const createSchema = z.object({
  campaign_id: z.string().uuid("Pick a campaign"),
  driver_profile_id: z.string().uuid("Pick a driver"),
  vehicle_id: z.string().uuid("Pick a vehicle"),
  creative_id: z.string().uuid("Select a ready creative"),
  expires_at: z.string().datetime({ offset: true }),
  notes: z
    .string()
    .trim()
    .max(500)
    .transform((v) => (v === "" ? null : v)),
  recommendation_context: z
    .object({
      service_city: z.string().trim().min(1).max(128),
      vehicle_type: z.literal("car"),
      matching_version: z.literal("matching_v1"),
      fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
    })
    .optional(),
});

const recommendationSchema = z.object({
  campaign_id: z.string().uuid("Pick a campaign"),
  service_city: z.string().trim().min(1, "Enter a service city").max(128),
});

function normalizeExpiry(value: FormDataEntryValue | null): FormDataEntryValue | null {
  if (typeof value !== "string" || !value) return value;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
}

export async function listAssignmentRecommendationsAction(
  values: unknown,
): Promise<AssignmentRecommendationActionState> {
  const parsed = recommendationSchema.safeParse(values);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data, error } = await api.GET("/api/v1/admin/campaign-assignments/recommendations", {
      params: { query: { ...parsed.data, limit: 50, offset: 0 } },
    });
    if (error || !data) return { error: "Could not load ranked candidates." };
    return { candidates: data.items };
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
}

export async function createAssignmentAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const recommendationParts = {
    service_city: formData.get("recommendation_service_city"),
    vehicle_type: formData.get("recommendation_vehicle_type"),
    matching_version: formData.get("recommendation_matching_version"),
    fingerprint: formData.get("recommendation_fingerprint"),
  };
  const hasRecommendationPart = Object.values(recommendationParts).some((value) => value !== null);
  const parsed = createSchema.safeParse({
    campaign_id: formData.get("campaign_id"),
    driver_profile_id: formData.get("driver_profile_id"),
    vehicle_id: formData.get("vehicle_id"),
    creative_id: formData.get("creative_id"),
    expires_at: normalizeExpiry(formData.get("expires_at")),
    notes: formData.get("notes") ?? "",
    recommendation_context: hasRecommendationPart ? recommendationParts : undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments", { body: parsed.data });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/assignments");
  redirect("/admin/assignments");
}

export async function cancelAssignmentAction(assignmentId: string): Promise<AdminActionState> {
  if (!z.string().uuid().safeParse(assignmentId).success) return { error: "Invalid assignment" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments/{assignment_id}/cancel", {
      params: { path: { assignment_id: assignmentId } },
      body: {},
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/assignments");
  return {};
}

export async function activateAssignmentAction(assignmentId: string): Promise<AdminActionState> {
  if (!z.string().uuid().safeParse(assignmentId).success) return { error: "Invalid assignment" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments/{assignment_id}/activate", {
      params: { path: { assignment_id: assignmentId } },
      body: {},
    });
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/assignments");
  return {};
}
