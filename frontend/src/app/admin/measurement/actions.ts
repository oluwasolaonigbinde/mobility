"use server";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { z } from "zod";
import type { components } from "@/lib/api/schema";
import { rerunCampaignReport } from "@/lib/api/audit-batch2";
import { requireRole } from "@/lib/auth/current-user";
import { redirect } from "next/navigation";

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
      revalidatePath("/admin/campaigns/[campaignId]", "page");
      return { report: data };
    }
    if (!p.issuance) return { error: "Select a recorded report first." };
    const { data: report } = await api.GET("/api/v1/admin/report-issuances/{issuance_id}", {
      params: { path: { issuance_id: p.issuance } },
    });
    if (!report || report.measurement_run_id !== p.run)
      return { error: "This report does not belong to the selected results." };
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
export type RerunState = {
  error?: string;
  report?: components["schemas"]["ReportIssuanceRead"];
  unknownOutcome?: boolean;
};
export async function rerunReportAction(
  campaignId: string,
  _state: RerunState,
): Promise<RerunState> {
  await requireRole("admin");
  if (!z.uuid().safeParse(campaignId).success) return { error: "Choose a campaign first." };
  try {
    const { data } = await rerunCampaignReport(
      createApiClient(await getSessionToken()),
      campaignId,
    );
    if (!data || data.campaign_id !== campaignId) return { unknownOutcome: true };
    revalidatePath(`/admin/campaigns/${campaignId}`);
    return { report: data };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && error.code === "REPORT_PERIOD_UNAVAILABLE")
      return { error: "There isn’t a completed reporting period for this campaign yet." };
    if (error instanceof ApiError && [403, 404].includes(error.status))
      return { error: "This campaign isn’t available to your account." };
    return { unknownOutcome: true };
  }
}
