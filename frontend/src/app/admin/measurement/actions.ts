"use server";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { z } from "zod";
import type { components } from "@/lib/api/schema";

export type ReportState = {
  error?: string;
  report?: components["schemas"]["ReportIssuanceRead"];
  download?: { url: string; filename: string };
};
export async function manageReport(_state: ReportState, form: FormData): Promise<ReportState> {
  const parsed = z
    .object({
      run: z.string().uuid(),
      request: z.string().uuid(),
      issuance: z.string().uuid().optional(),
      command: z.enum(["issue", "refresh", "csv", "pdf"]),
      reason: z.string().max(500),
    })
    .safeParse({
      run: form.get("run"),
      request: form.get("request"),
      issuance: form.get("issuance") || undefined,
      command: form.get("command"),
      reason: form.get("reason") ?? "",
    });
  if (!parsed.success) return { error: "The report request is incomplete. Reload and try again." };
  try {
    const api = createApiClient(await getSessionToken());
    const p = parsed.data;
    if (p.command === "issue") {
      const { data } = await api.POST("/api/v1/admin/measurement-runs/{run_id}/report-issuances", {
        params: { path: { run_id: p.run } },
        body: { client_request_id: p.request },
      });
      if (!data) return { error: "No report request was confirmed. Retry the same request." };
      revalidatePath("/admin/measurement");
      return { report: data };
    }
    if (!p.issuance) return { error: "Select a recorded report first." };
    const { data: report } = await api.GET("/api/v1/admin/report-issuances/{issuance_id}", {
      params: { path: { issuance_id: p.issuance } },
    });
    if (!report || report.measurement_run_id !== p.run)
      return { error: "This report does not belong to the selected snapshot." };
    if (p.command === "refresh") return { report };
    const { data } = await api.POST(
      "/api/v1/admin/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
      {
        params: { path: { issuance_id: p.issuance, artifact_format: p.command } },
        body: { reason: p.reason },
      },
    );
    return data
      ? { report, download: { url: data.url, filename: data.filename } }
      : { report, error: "No download was authorized." };
  } catch (error) {
    return {
      ..._state,
      download: undefined,
      error:
        error instanceof ApiError
          ? error.message
          : "Report service unavailable. Retry the same request; no completion is assumed.",
    };
  }
}
export async function issueMeasurement(_state: { error?: string; done?: string }, form: FormData) {
  const parsed = z
    .object({
      campaign_id: z.string().uuid(),
      client_request_id: z.string().uuid(),
      period_start_at: z.string().datetime(),
      period_end_at: z.string().datetime(),
      test_only: z.boolean(),
    })
    .safeParse({
      campaign_id: form.get("campaign_id"),
      client_request_id: form.get("client_request_id"),
      period_start_at: form.get("period_start_at"),
      period_end_at: form.get("period_end_at"),
      test_only: form.get("test_only") === "on",
    });
  if (!parsed.success)
    return { error: "Select a campaign and enter complete UTC period timestamps." };
  try {
    const { data } = await createApiClient(await getSessionToken()).POST(
      "/api/v1/admin/measurement-runs",
      { body: { ...parsed.data, mode: "performance_only" } },
    );
    if (!data) return { error: "No run was confirmed. Retry the same request." };
    revalidatePath("/admin/measurement");
    return {
      done: "Measurement run recorded. Open it to review completeness and reproduction before issuing a report.",
    };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? error.message
          : "Service unavailable. Retry the same request to recover its result.",
    };
  }
}
