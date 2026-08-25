"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface SourceActionState {
  error?: string;
  success?: string;
}

function text(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "").trim();
}

export async function createSourceAction(
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const sourceType = text(formData, "source_type");
  const expiresAt = new Date(text(formData, "expires_at"));
  if (!Number.isFinite(expiresAt.getTime()) || expiresAt <= new Date()) {
    return { error: "Choose a future expiry date and time." };
  }
  const common = {
    source_type: sourceType,
    provenance: "advertiser-declared",
    lawful_basis_reference: "candidate-legitimate-interest",
    lawful_basis_status: "unapproved",
    consent_disclaimer_status: "not-reviewed",
    expires_at: expiresAt.toISOString(),
    dsr_owner_role: "privacy-officer",
    dsr_status: "pending",
  };
  let body: Record<string, string | number>;
  if (sourceType === "website-traffic") {
    body = {
      ...common,
      audience_category: text(formData, "category"),
      aggregation_window_days: Number(text(formData, "window_days")),
    };
  } else if (sourceType === "digital-campaign-audience") {
    body = {
      ...common,
      channel: text(formData, "channel"),
      audience_stage: text(formData, "stage"),
      aggregation_window_days: Number(text(formData, "window_days")),
    };
  } else if (sourceType === "CRM-upload-reference") {
    body = {
      ...common,
      reference_mode: "aggregate-availability-only",
      record_count_band: text(formData, "count_band"),
    };
  } else if (sourceType === "UTM-source") {
    body = {
      ...common,
      channel: text(formData, "channel"),
      campaign_stage: text(formData, "stage"),
    };
  } else if (sourceType === "manual-insight") {
    body = {
      ...common,
      insight_category: text(formData, "category"),
      confidence_band: text(formData, "confidence"),
    };
  } else {
    return { error: "Choose an allowed planning source type." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-sources", {
      params: { header: { "Idempotency-Key": randomUUID() } },
      body: body as never,
    });
  } catch (error) {
    return { error: error instanceof ApiError ? error.message : "Could not reach the server." };
  }
  revalidatePath("/advertiser/planning-sources");
  return { success: "Planning source recorded." };
}

export async function deactivateSourceAction(sourceId: string): Promise<void> {
  const api = createApiClient(await getSessionToken());
  await api.POST("/api/v1/advertiser/retargeting-sources/{source_id}/deactivate", {
    params: {
      path: { source_id: sourceId },
      header: { "Idempotency-Key": randomUUID() },
    },
  });
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/planning-sources");
}

export async function createSourceLinkAction(
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const startAt = new Date(text(formData, "start_at"));
  const endAt = new Date(text(formData, "end_at"));
  if (
    !Number.isFinite(startAt.getTime()) ||
    !Number.isFinite(endAt.getTime()) ||
    startAt >= endAt
  ) {
    return { error: "Choose a valid linkage window with the start before the end." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-source-links", {
      params: { header: { "Idempotency-Key": randomUUID() } },
      body: {
        source_id: text(formData, "source_id"),
        campaign_id: text(formData, "campaign_id"),
        zone_id: text(formData, "zone_id"),
        start_at: startAt.toISOString(),
        end_at: endAt.toISOString(),
      },
    });
  } catch (error) {
    return { error: error instanceof ApiError ? error.message : "Could not reach the server." };
  }
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/planning-sources");
  return { success: "Planning source linked to the target zone." };
}

export async function removeSourceLinkAction(linkId: string): Promise<void> {
  const api = createApiClient(await getSessionToken());
  await api.POST("/api/v1/advertiser/retargeting-source-links/{link_id}/remove", {
    params: {
      path: { link_id: linkId },
      header: { "Idempotency-Key": randomUUID() },
    },
  });
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/planning-sources");
}
