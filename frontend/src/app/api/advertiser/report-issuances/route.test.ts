import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET as getStatus } from "./[issuanceId]/route";
import { GET as downloadArtifact } from "./[issuanceId]/artifacts/[format]/download/route";
import { POST as createIssuance } from "../measurement-runs/[runId]/report-issuances/route";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  createApiClient: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.getSessionToken }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.createApiClient }));

describe("report issuance BFF", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSessionToken.mockResolvedValue("http-only-token");
    mocks.createApiClient.mockReturnValue({ GET: mocks.get, POST: mocks.post });
  });

  it("keeps authorization server-side and binds create to the exact run and request identity", async () => {
    mocks.post.mockResolvedValue({ data: { id: "issuance", status: "queued" } });
    const response = await createIssuance(
      new Request("http://localhost", {
        method: "POST",
        body: JSON.stringify({ client_request_id: "request", reissue_of_id: null }),
      }),
      { params: Promise.resolve({ runId: "run" }) },
    );

    expect(response.status).toBe(202);
    expect(mocks.createApiClient).toHaveBeenCalledWith("http-only-token");
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/measurement-runs/{run_id}/report-issuances",
      {
        params: { path: { run_id: "run" } },
        body: { client_request_id: "request", reissue_of_id: null },
      },
    );
  });

  it("reads one issuance and turns a report-aware download into a no-store redirect", async () => {
    mocks.get.mockResolvedValue({ data: { id: "issuance", status: "ready" } });
    const status = await getStatus(new Request("http://localhost"), {
      params: Promise.resolve({ issuanceId: "issuance" }),
    });
    expect(status.status).toBe(200);

    mocks.post.mockResolvedValue({
      data: {
        url: "https://private.example/download",
        filename: "safe.pdf",
        checksum_sha256: "a".repeat(64),
      },
    });
    const download = await downloadArtifact(new Request("http://localhost"), {
      params: Promise.resolve({ issuanceId: "issuance", format: "pdf" }),
    });

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/report-issuances/{issuance_id}/artifacts/{artifact_format}/download",
      {
        params: { path: { issuance_id: "issuance", artifact_format: "pdf" } },
        body: { reason: "Download the approved campaign performance artifact" },
      },
    );
    expect(download.status).toBe(303);
    expect(download.headers.get("location")).toBe("https://private.example/download");
    expect(download.headers.get("cache-control")).toBe("no-store");
  });
});
