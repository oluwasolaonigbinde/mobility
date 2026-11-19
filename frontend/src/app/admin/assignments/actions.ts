"use server";

import { lagosLocalToApi } from "@/lib/campaigns/schema";
import { publicActionError } from "@/lib/api/public-action-error";
import { revalidatePath } from "next/cache";
import { redirect, unstable_rethrow } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface AdminActionState {
  error?: string;
  cityRequiredForDriver?: string;
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
  creative_id: z.string().uuid("Select approved artwork"),
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

const offerErrors = {
  FORBIDDEN_ROLE: "An active staff login is required to send a job offer.",
  CAMPAIGN_NOT_FOUND: "This campaign could not be found. Choose a campaign again.",
  DRIVER_PROFILE_NOT_FOUND: "This driver could not be found. Choose a driver again.",
  VEHICLE_NOT_FOUND: "This car could not be found. Choose a car again.",
  CAMPAIGN_NOT_ASSIGNABLE: "This campaign can't take job offers in its current status.",
  CAMPAIGN_EXPIRED: "This campaign has ended. You can no longer offer jobs for it.",
  COMPLETE_CAMPAIGN_WINDOW_REQUIRED: "Set the campaign’s start and end before offering jobs.",
  INVALID_OFFER_EXPIRY: "Choose an expiry in the future and within the campaign dates.",
  DRIVER_PROFILE_NOT_ACTIVE: "Choose a driver whose profile is active.",
  VEHICLE_NOT_ACTIVE: "Choose an active car.",
  VEHICLE_DRIVER_PROFILE_MISMATCH: "Choose a car that belongs to this driver.",
  DRIVER_PERSON_PAYEE_NOT_APPROVED: "Approve the driver’s identity and payment details first.",
  VEHICLE_APPROVAL_REQUIRED: "Approve the car before offering this job.",
  DUPLICATE_CAMPAIGN_VEHICLE_ASSIGNMENT: "This car already has a job or offer for this campaign.",
  ACTIVE_ASSIGNMENT_EXISTS_FOR_DRIVER: "This driver already has a running job.",
  ACTIVE_ASSIGNMENT_EXISTS_FOR_VEHICLE: "This car already has a running job.",
  APPROVED_CAMPAIGN_CREATIVE_REQUIRED: "Choose approved artwork before offering this job.",
  MANAGED_CLEAN_CREATIVE_REQUIRED:
    "Upload a new artwork file and have it approved before offering this job.",
  CREATIVE_CONTENT_IDENTITY_REQUIRED:
    "Upload a new artwork file and have it approved before offering this job.",
  CREATIVE_VERSION_REQUIRED: "Save and approve the artwork before offering this job.",
  DRIVER_SERVICE_AREA_REQUIRED: "Add the driver’s city before sending a job offer.",
  FROZEN_PAYOUT_TERMS_REQUIRED: "Set pay terms that are in effect before offering jobs.",
  TARGET_AREA_REQUIRED: "Add a campaign area before offering jobs.",
  CAMPAIGN_ZONE_GEOMETRY_REQUIRED: "Check that all campaign areas are drawn on the map.",
  CAMPAIGN_VERSION_REQUIRED: "Save the campaign details before offering jobs.",
  STALE_RECOMMENDATION: "Find drivers again and choose a current recommendation.",
};

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
    if (error || !data) return { error: "Could not load drivers and cars." };
    return { candidates: data.items };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) return { error: publicActionError(error) };
    return { error: "Could not reach the server." };
  }
}

export async function createAssignmentAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const expiresAt = lagosLocalToApi(String(formData.get("expires_at") ?? ""));
  if (!expiresAt || Date.parse(expiresAt) <= Date.now()) {
    return { error: "Choose a valid offer expiry in the future." };
  }
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
    expires_at: expiresAt,
    notes: formData.get("notes") ?? "",
    recommendation_context: hasRecommendationPart ? recommendationParts : undefined,
  });
  if (!parsed.success) {
    const field = parsed.error.issues[0]?.path[0];
    if (field === "recommendation_context") return { error: offerErrors.STALE_RECOMMENDATION };
    if (field === "notes") return { error: "Keep your notes to 500 characters or fewer." };
    return { error: "Choose a campaign, driver, car and approved artwork." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments", { body: parsed.data });
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError && error.code === "DRIVER_SERVICE_AREA_REQUIRED")
      return {
        error: offerErrors.DRIVER_SERVICE_AREA_REQUIRED,
        cityRequiredForDriver: parsed.data.driver_profile_id,
      };
    if (error instanceof ApiError) return { error: publicActionError(error, offerErrors) };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  redirect(`/admin/campaigns/${parsed.data.campaign_id}#drivers`);
}

export async function cancelAssignmentAction(
  assignmentId: string,
  reason: string,
): Promise<AdminActionState> {
  const parsed = z
    .object({ assignmentId: z.string().uuid(), reason: z.string().trim().min(1).max(1000) })
    .safeParse({ assignmentId, reason });
  if (!parsed.success) return { error: "A cancellation reason is required" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments/{assignment_id}/cancel", {
      params: { path: { assignment_id: parsed.data.assignmentId } },
      body: { reason: parsed.data.reason },
    });
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) return { error: publicActionError(error) };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  return {};
}

export async function activateAssignmentAction(assignmentId: string): Promise<AdminActionState> {
  if (!z.string().uuid().safeParse(assignmentId).success)
    return { error: "Something went wrong. Refresh and try again." };
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/campaign-assignments/{assignment_id}/activate", {
      params: { path: { assignment_id: assignmentId } },
      body: {},
    });
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) return { error: publicActionError(error) };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/campaigns");
  revalidatePath("/admin/campaigns/[campaignId]", "page");
  return {};
}
