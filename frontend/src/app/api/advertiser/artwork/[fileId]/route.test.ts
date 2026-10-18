import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ post: vi.fn(), token: vi.fn(), fetch: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
import { GET } from "./route";
const fileId = "00000000-0000-4000-8000-000000000001";
const input = { params: Promise.resolve({ fileId }) };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.token.mockResolvedValue("session");
  mocks.post.mockResolvedValue({ data: { url: "http://storage.local/signed" } });
  mocks.fetch.mockResolvedValue(
    new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": "image/png" } }),
  );
  vi.stubGlobal("fetch", mocks.fetch);
});
it("authorises the file on every preview and returns private uncached image bytes", async () => {
  const response = await GET(new Request("http://localhost/artwork"), input);
  expect(response.status).toBe(200);
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(response.headers.get("x-content-type-options")).toBe("nosniff");
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/files/{file_id}/download", {
    params: { path: { file_id: fileId } },
    body: { purpose: "campaign_preview", reason: "Campaign artwork preview" },
  });
  expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2, 3]);
});
it("never fetches storage for a signed-out request", async () => {
  mocks.token.mockResolvedValue(undefined);
  expect((await GET(new Request("http://localhost/artwork"), input)).status).toBe(401);
  expect(mocks.post).not.toHaveBeenCalled();
  expect(mocks.fetch).not.toHaveBeenCalled();
});
it.each([401, 403, 404])("does not fetch another tenant's or denied file: %s", async (status) => {
  mocks.post.mockRejectedValue(new ApiError(status, { code: "DENIED", message: "Private detail" }));
  const response = await GET(new Request("http://localhost/artwork"), input);
  expect(response.status).toBe(status);
  expect(await response.text()).toBe("");
  expect(mocks.fetch).not.toHaveBeenCalled();
});
it.each(["text/html", "image/svg+xml", "application/pdf"])(
  "refuses active or unsupported content %s",
  async (contentType) => {
    mocks.fetch.mockResolvedValue(
      new Response("untrusted", { headers: { "content-type": contentType } }),
    );
    expect((await GET(new Request("http://localhost/artwork"), input)).status).toBe(404);
  },
);
it("bounds declared image sizes", async () => {
  mocks.fetch.mockResolvedValue(
    new Response("bytes", {
      headers: { "content-type": "image/png", "content-length": String(26 * 1024 * 1024) },
    }),
  );
  expect((await GET(new Request("http://localhost/artwork"), input)).status).toBe(404);
});
it("refuses redirects and times out storage reads", async () => {
  await GET(new Request("http://localhost/artwork"), input);
  expect(mocks.fetch).toHaveBeenCalledWith(
    "http://storage.local/signed",
    expect.objectContaining({
      redirect: "error",
      cache: "no-store",
      signal: expect.any(AbortSignal),
    }),
  );
});
