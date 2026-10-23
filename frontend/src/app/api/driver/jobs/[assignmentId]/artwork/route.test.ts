import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ read: vi.fn(), token: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: (token: string) => ({ token }) }));
vi.mock("@/lib/api/audit-batch2", () => ({ readDriverJobArtwork: mocks.read }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
import { GET } from "./route";
const assignmentId = "00000000-0000-4000-8000-000000000001";
const input = { params: Promise.resolve({ assignmentId }) };
const request = () => new Request("http://localhost/api/driver/jobs/artwork");
beforeEach(() => {
  vi.resetAllMocks();
  mocks.token.mockResolvedValue("driver-session");
  mocks.read.mockResolvedValue({
    data: { url: "http://storage.local/signed-secret", expires_in_seconds: 60 },
  });
  mocks.fetch.mockImplementation(
    async () =>
      new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/png" } }),
  );
  vi.stubGlobal("fetch", mocks.fetch);
});
afterEach(() => vi.unstubAllGlobals());
it("reauthorises each request and streams private bytes without exposing the signed URL", async () => {
  for (let n = 0; n < 2; n++) {
    const response = await GET(request(), input);
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("location")).toBeNull();
    expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2, 3]);
  }
  expect(mocks.read).toHaveBeenCalledTimes(2);
  expect(mocks.read).toHaveBeenCalledWith({ token: "driver-session" }, assignmentId);
  expect(mocks.fetch).toHaveBeenCalledWith(
    "http://storage.local/signed-secret",
    expect.objectContaining({
      redirect: "error",
      cache: "no-store",
      signal: expect.any(AbortSignal),
    }),
  );
});
it("rejects invalid assignment routes before backend/storage access", async () => {
  const response = await GET(request(), { params: Promise.resolve({ assignmentId: "other" }) });
  expect(response.status).toBe(404);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(mocks.read).not.toHaveBeenCalled();
  expect(mocks.fetch).not.toHaveBeenCalled();
});
it("does not fetch private artwork without a session", async () => {
  mocks.token.mockResolvedValue(null);
  expect((await GET(request(), input)).status).toBe(401);
  expect(mocks.read).not.toHaveBeenCalled();
  expect(mocks.fetch).not.toHaveBeenCalled();
});
it.each([401, 403, 404, 409])(
  "preserves backend denial %s without storage calls or private details",
  async (status) => {
    mocks.read.mockRejectedValue(
      new ApiError(status, { code: "ARTWORK_UNAVAILABLE", message: "private detail" }),
    );
    const response = await GET(request(), input);
    expect(response.status).toBe(status);
    expect(await response.text()).toBe("");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(mocks.fetch).not.toHaveBeenCalled();
  },
);
it.each([0, -1, null])("refuses missing/expired authority before storage: %s", async (expiry) => {
  mocks.read.mockResolvedValue({
    data: { url: "http://storage.local/secret", expires_in_seconds: expiry },
  });
  expect((await GET(request(), input)).status).toBe(404);
  expect(mocks.fetch).not.toHaveBeenCalled();
});
it.each(["text/html", "image/svg+xml", "application/javascript"])(
  "refuses active MIME %s",
  async (mime) => {
    mocks.fetch.mockResolvedValue(new Response("unsafe", { headers: { "content-type": mime } }));
    expect((await GET(request(), input)).status).toBe(404);
  },
);
it.each([["application/pdf", "pdf"]])(
  "delivers %s only as a sandboxed attachment",
  async (mime, extension) => {
    mocks.fetch.mockResolvedValue(new Response("file", { headers: { "content-type": mime } }));
    const response = await GET(request(), input);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toBe(
      `attachment; filename="campaign-advert.${extension}"`,
    );
    expect(response.headers.get("content-security-policy")).toContain("sandbox");
  },
);
it("bounds declared and actual streamed sizes", async () => {
  mocks.fetch.mockResolvedValueOnce(
    new Response("bytes", {
      headers: { "content-type": "image/png", "content-length": String(26 * 1024 * 1024) },
    }),
  );
  expect((await GET(request(), input)).status).toBe(404);
  mocks.fetch.mockResolvedValueOnce(
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(new Uint8Array(26 * 1024 * 1024));
          controller.close();
        },
      }),
      { headers: { "content-type": "image/png" } },
    ),
  );
  expect((await GET(request(), input)).status).toBe(413);
});
it("degrades storage or redirect failure without exposing URL/error", async () => {
  mocks.fetch.mockRejectedValue(new Error("signed-secret"));
  const response = await GET(request(), input);
  expect(response.status).toBe(503);
  expect(await response.text()).toBe("");
});
