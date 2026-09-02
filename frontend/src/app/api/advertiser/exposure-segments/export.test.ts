import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST } from "./[segmentId]/export/route";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  createApiClient: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.getSessionToken }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.createApiClient }));

describe("aggregate targeting export BFF", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSessionToken.mockResolvedValue("http-only-token");
    mocks.createApiClient.mockReturnValue({ POST: mocks.post });
  });

  it("keeps authorization server-side and reuses the segment-bound operation identity", async () => {
    const segmentId = "00000000-0000-4000-8000-000000000066";
    mocks.post.mockResolvedValue({
      data: {
        csv_content: "campaign_id,coverage_cell\n1,grid-500m:1:1\n",
        csv_sha256: "a".repeat(64),
      },
    });

    const form = new FormData();
    form.set("approval_id", "00000000-0000-4000-8000-000000000075");
    const response = await POST(new Request("http://localhost", { method: "POST", body: form }), {
      params: Promise.resolve({ segmentId }),
    });

    expect(mocks.createApiClient).toHaveBeenCalledWith("http-only-token");
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/exposure-segments/{segment_id}/exports",
      {
        params: {
          path: { segment_id: segmentId },
          header: { "Idempotency-Key": `w3-01d-export-${segmentId}` },
        },
        body: { approval_id: "00000000-0000-4000-8000-000000000075" },
      },
    );
    expect(response.headers.get("content-type")).toBe("text/csv; charset=utf-8");
    expect(response.headers.get("x-content-sha256")).toBe("a".repeat(64));
  });
});
