"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";

export interface AdminActionState {
  error?: string;
  saved?: boolean;
}

function toState(error: unknown): AdminActionState {
  if (error instanceof ApiError) return { error: error.message };
  return { error: "Could not reach the server." };
}

// --- driver profiles ---------------------------------------------------------

const createDriverSchema = z.object({
  user_id: z.string().uuid("Pick the driver user"),
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

export async function createDriverProfileAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const parsed = createDriverSchema.safeParse({
    user_id: formData.get("user_id"),
    license_number: formData.get("license_number") ?? "",
    service_city: formData.get("service_city") ?? "",
    country_code: formData.get("country_code") ?? "",
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  const { user_id, ...profile } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/admin/drivers/{user_id}/profile", {
      params: { path: { user_id } },
      body: { ...profile, onboarding_status: "active" },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/admin/drivers");
  revalidatePath("/admin/drivers/[driverId]", "page");
  revalidatePath("/admin/drivers/applicant/[applicationId]", "page");
  redirect("/admin/drivers");
}

const onboardingSchema = z.object({
  driverProfileId: z.string().uuid(),
  status: z.enum(["pending", "active", "suspended", "rejected"]),
});

export async function updateDriverOnboardingAction(
  input: z.input<typeof onboardingSchema>,
): Promise<AdminActionState> {
  const parsed = onboardingSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid request" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/admin/drivers/{driver_profile_id}", {
      params: { path: { driver_profile_id: parsed.data.driverProfileId } },
      body: { onboarding_status: parsed.data.status },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/admin/drivers");
  revalidatePath("/admin/drivers/[driverId]", "page");
  revalidatePath("/admin/drivers/applicant/[applicationId]", "page");
  return {};
}

// --- vehicles ------------------------------------------------------------------

export async function updateDriverDetailsAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  await requireRole("admin");
  const parsed = createDriverSchema
    .extend({
      license_number: z
        .string()
        .trim()
        .max(128)
        .transform((v) => (v === "" ? null : v)),
      service_city: z
        .string()
        .trim()
        .max(128)
        .transform((v) => (v === "" ? null : v)),
    })
    .safeParse({
      user_id: formData.get("driver_profile_id"),
      license_number: formData.get("license_number") ?? "",
      service_city: formData.get("service_city") ?? "",
      country_code: formData.get("country_code") ?? "",
    });
  if (!parsed.success)
    return { error: parsed.error.issues[0]?.message ?? "Check the driver details." };
  const { user_id: driver_profile_id, ...body } = parsed.data;
  try {
    await createApiClient(await getSessionToken()).PATCH(
      "/api/v1/admin/drivers/{driver_profile_id}",
      {
        params: { path: { driver_profile_id } },
        body,
      },
    );
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/admin/drivers");
  revalidatePath("/admin/drivers/[driverId]", "page");
  return { saved: true };
}

const createVehicleSchema = z.object({
  user_id: z.string().uuid("Pick the driver user"),
  plate_number: z.string().trim().min(2, "Plate number is required").max(32),
  plate_country_code: z
    .string()
    .trim()
    .toUpperCase()
    .pipe(z.string().length(2, "Use a 2-letter code (e.g. NG)")),
  vehicle_type: z.enum(["car", "van", "minibus", "bus", "motorcycle", "tricycle", "other"]),
  make: z
    .string()
    .trim()
    .max(80)
    .transform((v) => (v === "" ? null : v)),
  model: z
    .string()
    .trim()
    .max(80)
    .transform((v) => (v === "" ? null : v)),
  year: z
    .string()
    .trim()
    .transform((v) => (v === "" ? null : Number(v)))
    .pipe(z.number().int().min(1980).max(2100).nullable()),
  color: z
    .string()
    .trim()
    .max(40)
    .transform((v) => (v === "" ? null : v)),
});

export async function createVehicleAction(
  _prev: AdminActionState,
  formData: FormData,
): Promise<AdminActionState> {
  const parsed = createVehicleSchema.safeParse({
    user_id: formData.get("user_id"),
    plate_number: formData.get("plate_number"),
    plate_country_code: formData.get("plate_country_code") ?? "NG",
    vehicle_type: formData.get("vehicle_type"),
    make: formData.get("make") ?? "",
    model: formData.get("model") ?? "",
    year: formData.get("year") ?? "",
    color: formData.get("color") ?? "",
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  const { user_id, ...vehicle } = parsed.data;
  let driverProfileId: string | undefined;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/admin/drivers/{user_id}/vehicles", {
      params: { path: { user_id } },
      body: { ...vehicle, status: "active" },
    });
    driverProfileId = data?.driver_profile_id;
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/admin/drivers");
  revalidatePath("/admin/drivers/[driverId]", "page");
  revalidatePath("/admin/drivers/applicant/[applicationId]", "page");
  redirect(
    driverProfileId
      ? `/admin/drivers/${driverProfileId}#cars`
      : "/admin/drivers?source=cars&tab=active",
  );
}

const vehicleStatusSchema = z.object({
  vehicleId: z.string().uuid(),
  status: z.enum(["pending", "active", "inactive", "suspended"]),
});

export async function updateVehicleStatusAction(
  input: z.input<typeof vehicleStatusSchema>,
): Promise<AdminActionState> {
  const parsed = vehicleStatusSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid request" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/admin/vehicles/{vehicle_id}", {
      params: { path: { vehicle_id: parsed.data.vehicleId } },
      body: { status: parsed.data.status },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath("/admin/drivers");
  revalidatePath("/admin/drivers/[driverId]", "page");
  revalidatePath("/admin/drivers/applicant/[applicationId]", "page");
  return {};
}
