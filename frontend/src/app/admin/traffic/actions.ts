"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface ProfileActionState {
  error?: string;
  saved?: boolean;
}

const num = (msg: string) =>
  z
    .string()
    .trim()
    .regex(/^\d+(\.\d{1,4})?$/, msg);

const optionalNum = z
  .string()
  .trim()
  .transform((v) => (v === "" ? undefined : v))
  .pipe(num("Enter a valid non-negative number").optional());

const profileSchema = z.object({
  profile_id: z
    .string()
    .trim()
    .transform((v) => (v === "" ? undefined : v))
    .pipe(z.string().uuid().optional()),
  expected_revision: z
    .string()
    .trim()
    .transform((v) => (v === "" ? undefined : Number(v)))
    .pipe(z.number().int().positive().optional()),
  expected_value_fingerprint: z
    .string()
    .trim()
    .transform((v) => (v === "" ? undefined : v))
    .pipe(
      z
        .string()
        .regex(/^[0-9a-f]{64}$/)
        .optional(),
    ),
  name: z.string().trim().min(1, "Profile name is required").max(255),
  description: z
    .string()
    .trim()
    .max(500)
    .transform((v) => (v === "" ? null : v)),
  traffic_density_per_km: num("Density per km is required (e.g. 120)"),
  dwell_impressions_per_minute: num("Dwell impressions/min is required (e.g. 3)"),
  morning_weight: optionalNum,
  midday_weight: optionalNum,
  evening_weight: optionalNum,
  night_weight: optionalNum,
  target_zone_weight: optionalNum,
  bonus_zone_weight: optionalNum,
  exclusion_zone_weight: optionalNum,
  is_default: z.string().transform((v) => v === "on"),
});

export async function saveProfileAction(
  _prev: ProfileActionState,
  formData: FormData,
): Promise<ProfileActionState> {
  const keys = [
    "profile_id",
    "expected_revision",
    "expected_value_fingerprint",
    "name",
    "description",
    "traffic_density_per_km",
    "dwell_impressions_per_minute",
    "morning_weight",
    "midday_weight",
    "evening_weight",
    "night_weight",
    "target_zone_weight",
    "bonus_zone_weight",
    "exclusion_zone_weight",
  ] as const;
  const raw: Record<string, string> = Object.fromEntries(
    keys.map((k) => [k, String(formData.get(k) ?? "")]),
  );
  raw.is_default = String(formData.get("is_default") ?? "");
  const parsed = profileSchema.safeParse(raw);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };

  const { profile_id, ...body } = parsed.data;
  try {
    const api = createApiClient(await getSessionToken());
    if (profile_id) {
      await api.PATCH("/api/v1/admin/traffic-density-profiles/{profile_id}", {
        params: { path: { profile_id } },
        body,
      });
    } else {
      // Create requires every weight; blanks become neutral multipliers
      // (exclusion defaults to 0 — exclusion zones are never billed).
      await api.POST("/api/v1/admin/traffic-density-profiles", {
        body: {
          ...body,
          morning_weight: body.morning_weight ?? "1.0",
          midday_weight: body.midday_weight ?? "1.0",
          evening_weight: body.evening_weight ?? "1.0",
          night_weight: body.night_weight ?? "1.0",
          target_zone_weight: body.target_zone_weight ?? "1.0",
          bonus_zone_weight: body.bonus_zone_weight ?? "1.0",
          exclusion_zone_weight: body.exclusion_zone_weight ?? "0",
          profile_type: "custom",
          road_category_weight: "1.0",
          status: "active",
        },
      });
    }
  } catch (error) {
    if (error instanceof ApiError) return { error: error.message };
    return { error: "Could not reach the server." };
  }
  revalidatePath("/admin/traffic");
  return { saved: true };
}
