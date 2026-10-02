"use server";

import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { toApiDatetime } from "@/lib/campaigns/schema";

export interface SourceActionState {
  error?: string;
  success?: string;
  operationKey?: string;
}

function text(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "").trim();
}

const DATETIME_LOCAL = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/;

/** A datetime-local field read as Nigeria time (WAT), or null when it isn't a valid time. */
function nigeriaTime(formData: FormData, field: string): Date | null {
  const value = text(formData, field);
  if (!DATETIME_LOCAL.test(value)) return null;
  try {
    return new Date(toApiDatetime(value) ?? "");
  } catch {
    return null;
  }
}

const OPERATION_KEY = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function operationKey(formData: FormData): string | null {
  const value = text(formData, "operation_key");
  return OPERATION_KEY.test(value) ? value : null;
}

export async function createSourceAction(
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const idempotencyKey = operationKey(formData);
  if (idempotencyKey === null) {
    return { error: "Refresh this page before retrying the operation." };
  }
  const sourceType = text(formData, "source_type");
  const expiresAt = nigeriaTime(formData, "expires_at");
  if (expiresAt === null || expiresAt <= new Date()) {
    return {
      error: "Choose a future date and time to stop using it.",
      operationKey: idempotencyKey,
    };
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
    return { error: "Choose what kind of audience this is.", operationKey: idempotencyKey };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-sources", {
      params: { header: { "Idempotency-Key": idempotencyKey } },
      body: body as never,
    });
  } catch (error) {
    return {
      error: error instanceof ApiError ? error.message : "Could not reach the server.",
      operationKey: idempotencyKey,
    };
  }
  revalidatePath("/advertiser/planning-sources");
  return { success: "Audience saved.", operationKey: idempotencyKey };
}

export async function deactivateSourceAction(
  sourceId: string,
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const idempotencyKey = operationKey(formData);
  if (idempotencyKey === null) {
    return { error: "Refresh this page before retrying the operation." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-sources/{source_id}/deactivate", {
      params: {
        path: { source_id: sourceId },
        header: { "Idempotency-Key": idempotencyKey },
      },
    });
  } catch (error) {
    return {
      error: error instanceof ApiError ? error.message : "Could not reach the server.",
      operationKey: idempotencyKey,
    };
  }
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/settings/audiences");
  return { success: "Audience no longer used.", operationKey: idempotencyKey };
}

export async function createSourceLinkAction(
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const idempotencyKey = operationKey(formData);
  if (idempotencyKey === null) {
    return { error: "Refresh this page before retrying the operation." };
  }
  const startAt = nigeriaTime(formData, "start_at");
  const endAt = nigeriaTime(formData, "end_at");
  if (startAt === null || endAt === null || startAt >= endAt) {
    return {
      error: "Choose a start date and time before the end.",
      operationKey: idempotencyKey,
    };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-source-links", {
      params: { header: { "Idempotency-Key": idempotencyKey } },
      body: {
        source_id: text(formData, "source_id"),
        campaign_id: text(formData, "campaign_id"),
        zone_id: text(formData, "zone_id"),
        start_at: startAt.toISOString(),
        end_at: endAt.toISOString(),
      },
    });
  } catch (error) {
    return {
      error: error instanceof ApiError ? error.message : "Could not reach the server.",
      operationKey: idempotencyKey,
    };
  }
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/settings/audiences");
  return {
    success: "Audience connected to the campaign area.",
    operationKey: idempotencyKey,
  };
}

export async function removeSourceLinkAction(
  linkId: string,
  _previous: SourceActionState,
  formData: FormData,
): Promise<SourceActionState> {
  const idempotencyKey = operationKey(formData);
  if (idempotencyKey === null) {
    return { error: "Refresh this page before retrying the operation." };
  }
  try {
    const api = createApiClient(await getSessionToken());
    await api.POST("/api/v1/advertiser/retargeting-source-links/{link_id}/remove", {
      params: {
        path: { link_id: linkId },
        header: { "Idempotency-Key": idempotencyKey },
      },
    });
  } catch (error) {
    return {
      error: error instanceof ApiError ? error.message : "Could not reach the server.",
      operationKey: idempotencyKey,
    };
  }
  revalidatePath("/advertiser/planning-sources");
  revalidatePath("/admin/settings/audiences");
  return { success: "Audience disconnected from the campaign area.", operationKey: idempotencyKey };
}
