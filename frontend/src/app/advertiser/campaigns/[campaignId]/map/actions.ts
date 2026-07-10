"use server";

import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import type { components } from "@/lib/api/schema";

const requestSchema = z.object({
  campaignId: z.string().uuid(),
  /** "west,south,east,north" in lon/lat */
  bbox: z
    .string()
    .regex(/^-?\d+(\.\d+)?(,-?\d+(\.\d+)?){3}$/, "bbox must be west,south,east,north"),
  metric: z.enum(["ping_count", "trip_count", "distance_m", "estimated_impressions"]),
});

export interface HeatmapResult {
  data?: components["schemas"]["HeatmapFeatureCollection"];
  error?: string;
}

export async function fetchHeatmapAction(
  input: z.input<typeof requestSchema>,
): Promise<HeatmapResult> {
  const parsed = requestSchema.safeParse(input);
  if (!parsed.success) return { error: "Invalid heatmap request" };
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}/heatmap", {
      params: {
        path: { campaign_id: parsed.data.campaignId },
        query: { bbox: parsed.data.bbox, metric: parsed.data.metric },
      },
    });
    return { data };
  } catch (error) {
    if (error instanceof ApiError) {
      // e.g. bbox too large for the backend's area cap — surface its message
      return { error: error.message };
    }
    return { error: "Could not reach the server. Please try again." };
  }
}
