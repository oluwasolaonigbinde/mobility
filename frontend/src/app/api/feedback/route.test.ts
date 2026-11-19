import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  token: vi.fn(),
  relay: { value: true },
  headers: new Headers({ "x-client-ip": "203.0.113.9" }),
}));
vi.mock("next/headers", () => ({ headers: async () => mocks.headers }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
vi.mock("@/lib/env", () => ({
  env: () => ({
    API_BASE_URL: "http://api.test",
    LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: mocks.relay.value,
  }),
}));

import { POST } from "./route";

const post = (body: string) =>
  POST(
    new Request("https://app.test/api/feedback", {
      method: "POST",
      body,
      headers: { "content-type": "application/json" },
    }),
  );
const note = JSON.stringify({
  name: "Ada",
  page_path: "/",
  message: "Hi",
  website: null,
  screenshot: null,
});

beforeEach(() => {
  mocks.token.mockReset().mockResolvedValue("session-jwt");
  mocks.relay.value = true;
  mocks.fetch.mockReset().mockResolvedValue(Response.json({ status: "received" }));
  vi.stubGlobal("fetch", mocks.fetch);
});

it("forwards the note with the relayed client IP and the session bearer", async () => {
  const response = await post(note);
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ status: "received" });
  const request = mocks.fetch.mock.calls[0]![0] as Request;
  expect(request.url).toBe("http://api.test/api/v1/feedback");
  expect(request.headers.get("x-client-ip")).toBe("203.0.113.9");
  expect(request.headers.get("authorization")).toBe("Bearer session-jwt");
  expect(await request.json()).toEqual(JSON.parse(note));
});

it("sends signed-out notes without a bearer and without an IP when relay is off", async () => {
  mocks.token.mockResolvedValue(undefined);
  mocks.relay.value = false;
  await post(note);
  const request = mocks.fetch.mock.calls[0]![0] as Request;
  expect(request.headers.get("authorization")).toBeNull();
  expect(request.headers.get("x-client-ip")).toBeNull();
});

it("refuses bodies over 1 MiB before calling the API", async () => {
  const response = await post("x".repeat(1024 * 1024 + 1));
  expect(response.status).toBe(413);
  expect(mocks.fetch).not.toHaveBeenCalled();
});

it("refuses malformed JSON", async () => {
  expect((await post("{")).status).toBe(422);
  expect(mocks.fetch).not.toHaveBeenCalled();
});

it("passes the rate limit through with Retry-After", async () => {
  mocks.fetch.mockResolvedValue(
    Response.json(
      { error: { code: "FEEDBACK_RATE_LIMITED", message: "Please wait" } },
      { status: 429, headers: { "retry-after": "321" } },
    ),
  );
  const response = await post(note);
  expect(response.status).toBe(429);
  expect(response.headers.get("retry-after")).toBe("321");
});

it("maps an unexpected upstream failure to 502", async () => {
  mocks.fetch.mockRejectedValue(new Error("network"));
  expect((await post(note)).status).toBe(502);
});
