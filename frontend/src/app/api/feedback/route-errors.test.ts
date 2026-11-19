import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => undefined }));
vi.mock("@/lib/env", () => ({
  env: () => ({ API_BASE_URL: "http://api.test", LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: false }),
}));

import { POST } from "./route";

const note = JSON.stringify({ name: "Ada", page_path: "/", message: "Hi" });
const post = (body: BodyInit | null, headers: Record<string, string> = {}) =>
  POST(
    new Request("https://app.test/api/feedback", {
      method: "POST",
      body,
      headers: { "content-type": "application/json", ...headers },
    }),
  );
const upstream = (status: number, headers: Record<string, string> = {}) =>
  Response.json(
    { error: { code: `UPSTREAM_${status}`, message: `upstream ${status}`, details: {} } },
    { status, headers },
  );

beforeEach(() => {
  mocks.fetch.mockReset();
  vi.stubGlobal("fetch", mocks.fetch);
});

it.each([404, 413, 415, 422, 503])(
  "passes an upstream %s through with its code and no caching",
  async (status) => {
    mocks.fetch.mockResolvedValue(upstream(status));
    const response = await post(note);
    expect(response.status).toBe(status);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect((await response.json()).error.code).toBe(`UPSTREAM_${status}`);
  },
);

it("hides other upstream errors behind 502", async () => {
  mocks.fetch.mockResolvedValue(upstream(500));
  const response = await post(note);
  expect(response.status).toBe(502);
  expect((await response.json()).error.code).toBe("FEEDBACK_UNAVAILABLE");
});

it("defaults Retry-After to 60 seconds when the API sends none", async () => {
  mocks.fetch.mockResolvedValue(upstream(429));
  const response = await post(note);
  expect(response.status).toBe(429);
  expect(response.headers.get("retry-after")).toBe("60");
});

it("refuses a declared oversize body without reading it, and an empty body as invalid", async () => {
  expect((await post(note, { "content-length": String(2 * 1024 * 1024) })).status).toBe(413);
  expect((await post(null)).status).toBe(422);
  expect(mocks.fetch).not.toHaveBeenCalled();
});
