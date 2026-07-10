"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { validateZoneGeometry, type ZoneGeometry } from "@/lib/zones/geometry";

const ZONE_TYPES = ["target", "bonus", "exclusion"] as const;

const baseFields = {
  campaignId: z.string().uuid(),
  name: z.string().trim().min(1, "Zone name is required").max(255),
  zoneType: z.enum(ZONE_TYPES),
};

const createZoneSchema = z.object({
  ...baseFields,
  geometry: z.custom<ZoneGeometry>((g) => validateZoneGeometry(g).ok, {
    message: "Invalid zone geometry",
  }),
});

const updateZoneSchema = z.object({
  ...baseFields,
  zoneId: z.string().uuid(),
});

const deleteZoneSchema = z.object({
  campaignId: z.string().uuid(),
  zoneId: z.string().uuid(),
});

export interface ZoneActionState {
  error?: string;
}

function toState(error: unknown): ZoneActionState {
  if (error instanceof ApiError) return { error: error.message };
  return { error: "Could not reach the server. Please try again." };
}

export async function createZoneAction(
  input: z.input<typeof createZoneSchema>,
): Promise<ZoneActionState> {
  const parsed = createZoneSchema.safeParse(input);
  if (!parsed.success) {
    // Give the precise geometry reason when that's what failed.
    const geomCheck = validateZoneGeometry(input.geometry);
    return {
      error: !geomCheck.ok
        ? geomCheck.reason
        : (parsed.error.issues[0]?.message ?? "Invalid input"),
    };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
      params: { path: { campaign_id: parsed.data.campaignId } },
      body: {
        name: parsed.data.name,
        zone_type: parsed.data.zoneType,
        // The OpenAPI schema types geometry as an opaque object; ours is
        // structurally a valid GeoJSON Polygon/MultiPolygon (validated above).
        geometry: parsed.data.geometry as unknown as Record<string, unknown>,
      },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}/zones`);
  return {};
}

export async function updateZoneAction(
  input: z.input<typeof updateZoneSchema>,
): Promise<ZoneActionState> {
  const parsed = updateZoneSchema.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Invalid input" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.PATCH("/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}", {
      params: {
        path: { campaign_id: parsed.data.campaignId, zone_id: parsed.data.zoneId },
      },
      body: { name: parsed.data.name, zone_type: parsed.data.zoneType },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}/zones`);
  return {};
}

export async function deleteZoneAction(
  input: z.input<typeof deleteZoneSchema>,
): Promise<ZoneActionState> {
  const parsed = deleteZoneSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid delete request" };
  try {
    const api = createApiClient(await getSessionToken());
    await api.DELETE("/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}", {
      params: {
        path: { campaign_id: parsed.data.campaignId, zone_id: parsed.data.zoneId },
      },
    });
  } catch (error) {
    return toState(error);
  }
  revalidatePath(`/advertiser/campaigns/${parsed.data.campaignId}/zones`);
  return {};
}
