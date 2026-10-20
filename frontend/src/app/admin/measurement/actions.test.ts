import { beforeEach, describe, expect, it, vi } from "vitest";
import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), rerun: vi.fn() }));
vi.mock("@/lib/api/audit-batch2", () => ({ rerunCampaignReport: mocks.rerun }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: async () => ({ role: "admin" }) }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => mocks }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "test" }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
import { rerunReportAction, manageReport } from "./actions";
const run = "11111111-1111-4111-8111-111111111111";
const request = "22222222-2222-4222-8222-222222222222";
const issuance = "33333333-3333-4333-8333-333333333333";
function form(command: string) {
  const f = new FormData();
  Object.entries({
    run,
    request,
    issuance,
    command,
    reason: "Operator reviewing campaign results",
  }).forEach(([k, v]) => f.set(k, v));
  return f;
}
beforeEach(() => vi.clearAllMocks());
it("refuses a report belonging to another snapshot before authorizing a download", async () => {
  mocks.GET.mockResolvedValue({ data: { id: issuance, measurement_run_id: request } });
  const result = await manageReport({}, form("pdf"));
  expect(result.error).toMatch(/does not belong/);
  expect(mocks.POST).not.toHaveBeenCalled();
});
it("retains the same request identity after a lost report issuance response", async () => {
  mocks.POST.mockRejectedValueOnce(new Error("private upstream token"));
  expect((await manageReport({}, form("issue"))).error).toMatch(/Retry the same request/);
  mocks.POST.mockResolvedValueOnce({
    data: { id: issuance, measurement_run_id: run, status: "queued" },
  });
  const recovered = await manageReport({}, form("issue"));
  expect(recovered.report?.status).toBe("queued");
  for (const call of mocks.POST.mock.calls) expect(call[1].body.client_request_id).toBe(request);
  expect(recovered.download).toBeUndefined();
});
it("uses the protected artifact action only after reading the matching report", async () => {
  mocks.GET.mockResolvedValue({ data: { id: issuance, measurement_run_id: run, status: "ready" } });
  mocks.POST.mockResolvedValue({
    data: { url: "https://files.example.test/report", filename: "analysis.pdf" },
  });
  expect((await manageReport({}, form("pdf"))).download?.filename).toBe("analysis.pdf");
  expect(mocks.POST).toHaveBeenCalledWith(
    "/api/v1/admin/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
    expect.objectContaining({ body: { reason: "Operator reviewing campaign results" } }),
  );
});
it("rejects an incomplete report request before any API read", async () => {
  const f = form("export");
  expect(await manageReport({}, f)).toEqual({
    error: "The report request is incomplete. Reload and try again.",
  });
  expect(mocks.GET).not.toHaveBeenCalled();
  expect(mocks.POST).not.toHaveBeenCalled();
});
it("reports an unconfirmed issuance without revalidating", async () => {
  mocks.POST.mockResolvedValue({ data: undefined });
  expect(await manageReport({}, form("issue"))).toEqual({
    error: "No report request was confirmed. Retry the same request.",
  });
  expect(revalidatePath).not.toHaveBeenCalled();
});
it("revalidates the work list after a confirmed issuance", async () => {
  mocks.POST.mockResolvedValue({ data: { id: issuance, measurement_run_id: run } });
  await manageReport({}, form("issue"));
  expect(mocks.POST).toHaveBeenCalledWith(
    "/api/v1/admin/measurement-runs/{run_id}/report-issuances",
    { params: { path: { run_id: run } }, body: { client_request_id: request } },
  );
  expect(revalidatePath).toHaveBeenCalledWith("/admin/campaigns/[campaignId]", "page");
});
it("requires a recorded report before refreshing or downloading", async () => {
  const f = form("refresh");
  f.delete("issuance");
  expect(await manageReport({}, f)).toEqual({ error: "Select a recorded report first." });
  expect(mocks.GET).not.toHaveBeenCalled();
});
it("refreshes the matching report status without authorizing a download", async () => {
  const report = { id: issuance, measurement_run_id: run, status: "ready" };
  mocks.GET.mockResolvedValue({ data: report });
  expect(await manageReport({}, form("refresh"))).toEqual({ report });
  expect(mocks.GET).toHaveBeenCalledWith("/api/v1/admin/report-issuances/{issuance_id}", {
    params: { path: { issuance_id: issuance } },
  });
  expect(mocks.POST).not.toHaveBeenCalled();
});
it("treats a missing report read as not belonging to the snapshot", async () => {
  mocks.GET.mockResolvedValue({ data: undefined });
  expect((await manageReport({}, form("csv"))).error).toMatch(/does not belong/);
  expect(mocks.POST).not.toHaveBeenCalled();
});
it("keeps the report but reports an unauthorized download with an empty reason", async () => {
  const report = { id: issuance, measurement_run_id: run, status: "ready" };
  mocks.GET.mockResolvedValue({ data: report });
  mocks.POST.mockResolvedValue({ data: undefined });
  const f = form("csv");
  f.delete("reason");
  expect(await manageReport({}, f)).toEqual({ report, error: "No download was authorized." });
  expect(mocks.POST).toHaveBeenCalledWith(
    "/api/v1/admin/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
    { params: { path: { issuance_id: issuance, artifact_format: "csv" } }, body: { reason: "" } },
  );
});
it("keeps the previous report but drops any old download link on an API refusal", async () => {
  const previous = {
    report: { id: issuance, measurement_run_id: run } as never,
    download: { url: "https://files.example.test/old", filename: "old.pdf" },
  };
  mocks.GET.mockResolvedValue({ data: { id: issuance, measurement_run_id: run } });
  mocks.POST.mockRejectedValue(
    new ApiError(403, { code: "REPORT_ACCESS_DENIED", message: "Report access is not permitted." }),
  );
  expect(await manageReport(previous, form("pdf"))).toEqual({
    report: previous.report,
    download: undefined,
    error: "Report access is not permitted.",
  });
});
describe("rerunReportAction", () => {
  const campaign = "44444444-4444-4444-8444-444444444444";
  it("requests a fresh report through the bodyless campaign-bound capability", async () => {
    const report = {
      id: issuance,
      campaign_id: campaign,
      measurement_run_id: run,
      status: "queued",
    };
    mocks.rerun.mockResolvedValue({ data: report });
    expect(await rerunReportAction(campaign, {})).toEqual({ report });
    expect(mocks.rerun).toHaveBeenCalledWith(expect.anything(), campaign);
    expect(revalidatePath).toHaveBeenCalledWith(`/admin/campaigns/${campaign}`);
  });
  it("does not request results for a malformed campaign", async () => {
    expect(await rerunReportAction("bad", {})).toHaveProperty("error");
    expect(mocks.rerun).not.toHaveBeenCalled();
  });
  it("explains a missing completed reporting period", async () => {
    mocks.rerun.mockRejectedValue(
      new ApiError(409, { code: "REPORT_PERIOD_UNAVAILABLE", message: "private details" }),
    );
    expect(await rerunReportAction(campaign, {})).toHaveProperty(
      "error",
      "There isn’t a completed reporting period for this campaign yet.",
    );
  });
  it.each([undefined, { campaign_id: request }])(
    "does not claim a malformed confirmation succeeded",
    async (data) => {
      mocks.rerun.mockResolvedValue({ data });
      expect(await rerunReportAction(campaign, {})).toEqual({ unknownOutcome: true });
      expect(revalidatePath).not.toHaveBeenCalled();
    },
  );
  it("does not auto-retry a lost non-idempotent request", async () => {
    mocks.rerun.mockRejectedValue(new Error("lost response"));
    expect(await rerunReportAction(campaign, {})).toEqual({ unknownOutcome: true });
    expect(mocks.rerun).toHaveBeenCalledTimes(1);
    expect(revalidatePath).not.toHaveBeenCalled();
  });
});
