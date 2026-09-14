import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => mocks }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "test" }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
import { manageReport } from "./actions";
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
