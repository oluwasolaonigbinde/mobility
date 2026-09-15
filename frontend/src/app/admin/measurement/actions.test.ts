import { beforeEach, describe, expect, it, vi } from "vitest";
import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => mocks }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "test" }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
import { issueMeasurement, manageReport } from "./actions";
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
  expect(revalidatePath).toHaveBeenCalledWith("/admin/measurement");
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
describe("issueMeasurement", () => {
  const campaign = "44444444-4444-4444-8444-444444444444";
  function runForm(overrides: Record<string, string | null> = {}) {
    const f = new FormData();
    Object.entries({
      campaign_id: campaign,
      client_request_id: request,
      period_start_at: "2026-09-01T00:00:00Z",
      period_end_at: "2026-10-01T00:00:00Z",
      ...overrides,
    }).forEach(([k, v]) => (v === null ? f.delete(k) : f.set(k, v)));
    return f;
  }
  it.each([
    ["a missing campaign", { campaign_id: "" }],
    ["a local timestamp", { period_start_at: "2026-09-01 00:00" }],
    ["a missing request identity", { client_request_id: null }],
  ])("rejects %s without creating a run", async (_label, overrides) => {
    expect(await issueMeasurement({}, runForm(overrides))).toEqual({
      error: "Select a campaign and enter complete UTC period timestamps.",
    });
    expect(mocks.POST).not.toHaveBeenCalled();
  });
  it("creates a performance-only run and revalidates the work list", async () => {
    mocks.POST.mockResolvedValue({ data: { id: run } });
    const result = await issueMeasurement({}, runForm({ test_only: "on" }));
    expect(mocks.POST).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/measurement-runs", {
      body: {
        campaign_id: campaign,
        client_request_id: request,
        period_start_at: "2026-09-01T00:00:00Z",
        period_end_at: "2026-10-01T00:00:00Z",
        test_only: true,
        mode: "performance_only",
      },
    });
    expect(revalidatePath).toHaveBeenCalledWith("/admin/measurement");
    expect(result.done).toMatch(/^Measurement run recorded/);
  });
  it("records a live-data run when the synthetic box is unchecked", async () => {
    mocks.POST.mockResolvedValue({ data: { id: run } });
    await issueMeasurement({}, runForm());
    expect(mocks.POST.mock.calls[0]![1].body.test_only).toBe(false);
  });
  it("does not claim a run without a confirmed response", async () => {
    mocks.POST.mockResolvedValue({ data: undefined });
    expect(await issueMeasurement({}, runForm())).toEqual({
      error: "No run was confirmed. Retry the same request.",
    });
    expect(revalidatePath).not.toHaveBeenCalled();
  });
  it("maps API refusals to their message and other failures to a retry instruction", async () => {
    mocks.POST.mockRejectedValueOnce(
      new ApiError(409, {
        code: "MEASUREMENT_METHOD_NOT_APPROVED",
        message: "Method not approved.",
      }),
    );
    expect(await issueMeasurement({}, runForm())).toEqual({ error: "Method not approved." });
    mocks.POST.mockRejectedValueOnce(new Error("socket closed"));
    expect(await issueMeasurement({}, runForm())).toEqual({
      error: "Service unavailable. Retry the same request to recover its result.",
    });
  });
});
