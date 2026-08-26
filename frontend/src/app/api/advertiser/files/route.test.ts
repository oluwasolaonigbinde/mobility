import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST as createUpload } from "./uploads/route";
import { POST as confirmUpload } from "./uploads/[uploadId]/confirm/route";
import { GET as getFile } from "./[fileId]/route";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  createApiClient: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.getSessionToken }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.createApiClient }));

describe("advertiser file BFF routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSessionToken.mockResolvedValue("http-only-token");
    mocks.createApiClient.mockReturnValue({ GET: mocks.get, POST: mocks.post });
  });

  it("keeps API authorization server-side across upload, confirm, and scan polling", async () => {
    mocks.post
      .mockResolvedValueOnce({
        data: { upload_id: "upload-1", upload: { url: "http://storage", fields: {} } },
      })
      .mockResolvedValueOnce({ data: { id: "file-1", scan_status: "pending" } });
    mocks.get.mockResolvedValueOnce({ data: { id: "file-1", scan_status: "clean" } });

    const body = {
      client_request_id: "00000000-0000-4000-8000-000000000001",
      purpose: "creative",
      filename: "wrap.png",
      content_type: "image/png",
      size_bytes: 10,
      sha256: "a".repeat(64),
    };
    await createUpload(
      new Request("http://localhost/api/advertiser/files/uploads", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    );
    await confirmUpload(new Request("http://localhost"), {
      params: Promise.resolve({ uploadId: "upload-1" }),
    });
    await getFile(new Request("http://localhost"), {
      params: Promise.resolve({ fileId: "file-1" }),
    });

    expect(mocks.createApiClient).toHaveBeenCalledWith("http-only-token");
    expect(mocks.post).toHaveBeenNthCalledWith(1, "/api/v1/advertiser/files/uploads", {
      body,
    });
    expect(mocks.post).toHaveBeenNthCalledWith(
      2,
      "/api/v1/advertiser/files/uploads/{upload_id}/confirm",
      { params: { path: { upload_id: "upload-1" } } },
    );
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/files/{file_id}", {
      params: { path: { file_id: "file-1" } },
    });
  });
});
