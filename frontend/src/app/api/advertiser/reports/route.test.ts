import { beforeEach, expect, it, vi } from "vitest";
import { GET, POST } from "./route";
import { GET as download } from "./[reportId]/download/route";
import { GET as artwork } from "./artwork/[fileId]/route";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ token: vi.fn(), client: vi.fn(), get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
vi.mock("@/lib/api/client", () => ({ createApiClient: mocks.client }));
// REQ-316 F9: path ids must be UUIDs, so the download fixtures use one.
const reportId = "00000000-0000-4000-8000-0000000000d1";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.token.mockResolvedValue("server-session");
  mocks.client.mockReturnValue({ GET: mocks.get, POST: mocks.post });
});

it("keeps the session server-side and sends the same chosen-period request", async () => {
  const body = {
    client_request_id: "request",
    start_date: "2020-01-01",
    end_date: "2020-01-02",
    campaign_id: null,
  };
  mocks.post.mockResolvedValue({ data: { id: "report", status: "queued" } });
  const result = await POST(
    new Request("http://localhost/api/advertiser/reports", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
  expect(result.status).toBe(202);
  expect(mocks.client).toHaveBeenCalledWith("server-session");
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/reports", { body });
  expect(result.headers.get("cache-control")).toBe("no-store");
});

it("lists one campaign without returning a session token", async () => {
  mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
  const result = await GET(
    new Request("http://localhost/api/advertiser/reports?campaign_id=campaign&offset=25"),
  );
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/reports", {
    params: { query: { campaign_id: "campaign", offset: 25, limit: 25 } },
  });
  expect(JSON.stringify(await result.json())).not.toContain("server-session");
});

it.each([false, true])(
  "downloads new and issued files through the correct owned read (%s)",
  async (legacy) => {
    mocks.post.mockResolvedValue({
      data: { url: "https://private.test/file", checksum_sha256: "a".repeat(64) },
    });
    const result = await download(
      new Request(
        `http://localhost/api/advertiser/reports/${reportId}/download?format=pdf&legacy=${legacy}`,
      ),
      {
        params: Promise.resolve({ reportId }),
      },
    );
    expect(result.status).toBe(303);
    expect(result.headers.get("location")).toBe("https://private.test/file");
    expect(result.headers.get("cache-control")).toBe("no-store");
    expect(mocks.post.mock.calls[0]?.[0]).toBe(
      legacy
        ? "/api/v1/advertiser/report-issuances/{issuance_id}/artifacts/{artifact_format}/download"
        : "/api/v1/advertiser/reports/{report_id}/artifacts/{artifact_format}/download",
    );
  },
);

it("rejects an unsupported format before any backend or storage request", async () => {
  const result = await download(
    new Request(`http://localhost/api/advertiser/reports/${reportId}/download?format=html`),
    {
      params: Promise.resolve({ reportId }),
    },
  );
  expect(result.status).toBe(404);
  expect(mocks.client).not.toHaveBeenCalled();
});

it("opens a file-specific report artwork reference through the existing guarded download", async () => {
  mocks.post.mockResolvedValue({ data: { url: "https://private.test/scanned-artwork.pdf" } });
  const fileId = "00000000-0000-4000-8000-000000000001";
  const result = await artwork(
    new Request(`http://localhost/api/advertiser/reports/artwork/${fileId}`),
    {
      params: Promise.resolve({ fileId }),
    },
  );
  expect(result.status).toBe(303);
  expect(result.headers.get("location")).toBe("https://private.test/scanned-artwork.pdf");
  expect(result.headers.get("cache-control")).toBe("private, no-store");
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/files/{file_id}/download", {
    params: { path: { file_id: fileId } },
    body: { purpose: "campaign_preview", reason: "Report artwork preview" },
  });
});

it.each([404, 409])("retains file ownership and uncleared-scan denial (%s)", async (status) => {
  mocks.post.mockRejectedValue(
    new ApiError(status, { code: "FILE_DENIED", message: "File unavailable" }),
  );
  const result = await artwork(
    new Request("http://localhost/api/advertiser/reports/artwork/file"),
    {
      params: Promise.resolve({ fileId: "00000000-0000-4000-8000-000000000001" }),
    },
  );
  expect(result.status).toBe(status);
  expect(result.headers.get("location")).toBeNull();
  expect(result.headers.get("cache-control")).toBe("private, no-store");
});

it.each([
  "javascript:alert(1)",
  "data:text/html,hi",
  "https://user:secret@private.test/artwork.pdf",
  "not a url",
])("never redirects report artwork to an unsafe storage URL: %s", async (url) => {
  mocks.post.mockResolvedValue({ data: { url } });
  const fileId = "00000000-0000-4000-8000-000000000001";
  const result = await artwork(
    new Request(`http://localhost/api/advertiser/reports/artwork/${fileId}`),
    { params: Promise.resolve({ fileId }) },
  );
  expect(result.status).toBe(404);
  expect(result.headers.get("location")).toBeNull();
});

function create() {
  return POST(
    new Request("http://localhost/api/advertiser/reports", {
      method: "POST",
      body: JSON.stringify({ client_request_id: "request" }),
    }),
  );
}

it.each([
  [409, "REPORT_NO_CAMPAIGNS", "There are no campaigns to report on."],
  [422, "REPORT_TOO_LARGE", "Choose fewer campaigns or a shorter reporting period."],
  [
    409,
    "REPORT_REQUEST_CONFLICT",
    "This request was already used. Refresh the page and try again.",
  ],
])("maps the %s %s create refusal to fixed copy", async (status, code, message) => {
  mocks.post.mockRejectedValue(
    new ApiError(status, {
      code,
      message: "internal backend detail",
      details: { secret: "x" },
      request_id: "req-1",
    }),
  );
  const result = await create();
  expect(result.status).toBe(status);
  expect(result.headers.get("cache-control")).toBe("no-store");
  expect(await result.json()).toEqual({
    error: { code, message, details: {}, request_id: "req-1" },
  });
});

it("gives an unknown create refusal the generic fallback without leaking", async () => {
  mocks.post.mockRejectedValue(
    new ApiError(400, { code: "SOMETHING_ELSE", message: "internal backend detail" }),
  );
  const result = await create();
  const json = await result.json();
  expect(result.status).toBe(400);
  expect(json.error.message).toBe("That didn't work. Try again.");
  expect(JSON.stringify(json)).not.toContain("internal backend detail");
});
