"use server";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { z } from "zod";

export type SelectionKind = "campaign" | "driver" | "vehicle" | "creative";
export type SelectionOption = {
  id: string;
  label: string;
  detail: string;
  unavailable?: string;
  fileId?: string;
};
export async function searchOperatorOptions(input: {
  kind: SelectionKind;
  q: string;
  offset: number;
  parentId?: string;
}): Promise<{ items: SelectionOption[]; total: number; error?: string }> {
  const parsed = z
    .object({
      kind: z.enum(["campaign", "driver", "vehicle", "creative"]),
      q: z.string().max(120),
      offset: z.number().int().nonnegative(),
      parentId: z.string().uuid().optional(),
    })
    .safeParse(input);
  if (!parsed.success) return { items: [], total: 0, error: "Select a valid search." };
  const { kind, q, offset, parentId } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    if (kind === "campaign") {
      const { data } = await api.GET("/api/v1/admin/campaigns", {
        params: { query: { q, limit: 25, offset } },
      });
      if (!data) throw new Error();
      return {
        total: data.total,
        items: data.items.map((c) => ({
          id: c.id,
          label: c.name,
          detail: `${c.status} · ${c.id.slice(0, 8)}`,
          unavailable: ["approved", "scheduled", "active"].includes(c.status)
            ? undefined
            : "Campaign approval required",
        })),
      };
    }
    if (kind === "driver") {
      const { data } = await api.GET("/api/v1/admin/drivers", {
        params: { query: { q, limit: 25, offset } },
      });
      if (!data) throw new Error();
      return {
        total: data.total,
        items: data.items.map((d) => ({
          id: d.id,
          label: d.full_name,
          detail: `${d.email} · ${d.service_city ?? "No city"}`,
          unavailable:
            d.onboarding_status === "active" ? undefined : `Driver ${d.onboarding_status}`,
        })),
      };
    }
    if (kind === "vehicle") {
      if (!parentId) return { items: [], total: 0, error: "Select a driver first." };
      const { data } = await api.GET("/api/v1/admin/vehicles", {
        params: { query: { q, limit: 25, offset, driver_profile_id: parentId } },
      });
      if (!data) throw new Error();
      return {
        total: data.total,
        items: data.items.map((v) => ({
          id: v.id,
          label: v.plate_number,
          detail: [v.make, v.model, v.status].filter(Boolean).join(" · "),
          unavailable:
            v.status === "active" && v.vehicle_type === "car"
              ? undefined
              : "An active approved car is required",
        })),
      };
    }
    if (!parentId) return { items: [], total: 0, error: "Select a campaign first." };
    const { data } = await api.GET("/api/v1/admin/campaigns/{campaign_id}/creatives", {
      params: { path: { campaign_id: parentId }, query: { limit: 25, offset } },
    });
    if (!data) throw new Error();
    return {
      total: data.total,
      items: data.items.map((c) => ({
        id: c.id,
        label: c.name,
        detail: `${c.placement} · ${c.status} · ${c.id.slice(0, 8)}`,
        fileId: c.stored_file_id ?? undefined,
        unavailable:
          c.status === "approved" && c.scan_status === "clean"
            ? undefined
            : "Approved, scan-clean artwork is required",
      })),
    };
  } catch {
    return { items: [], total: 0, error: "Selection list is unavailable. Try again." };
  }
}

export async function previewOperatorArtwork(
  fileId: string,
): Promise<{ url?: string; error?: string }> {
  if (!z.string().uuid().safeParse(fileId).success) return { error: "Select current artwork." };
  try {
    const { data } = await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/files/{file_id}/download",
      {
        params: { path: { file_id: fileId } },
        body: { purpose: "creative_review", reason: "Assignment artwork selection" },
      },
    );
    return { url: data?.url };
  } catch {
    return {
      error:
        "Artwork preview is unavailable. Approval and file safety are rechecked when offering.",
    };
  }
}
