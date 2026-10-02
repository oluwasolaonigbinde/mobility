import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import proxy from "./proxy";

vi.mock("@/lib/auth/token", () => ({ tokenNeedsRefresh: vi.fn(() => true) }));

function request(path: string, withCookie = true) {
  return new NextRequest(`http://localhost${path}`, {
    headers: withCookie ? { cookie: "mobility_session=expired-token" } : undefined,
  });
}

describe("driver proxy session transitions", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the public manifest reachable without a cookie", async () => {
    const response = await proxy(request("/driver/manifest.webmanifest", false));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("clears a cookie when refresh proves the session revoked", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));
    const response = await proxy(request("/driver/track"));
    expect(response.headers.get("set-cookie")).toMatch(/mobility_session=;/);
  });

  it("retains the still-valid cookie when the refresh provider is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const response = await proxy(request("/driver/track"));
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});

it("overwrites a caller's admin pathname hint and strips it from other pages", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
  const admin = await proxy(
    new NextRequest("http://localhost/admin/settings/staff", {
      headers: { cookie: "mobility_session=token", "x-cardvert-admin-path": "/admin" },
    }),
  );
  expect(admin.headers.get("x-middleware-request-x-cardvert-admin-path")).toBe(
    "/admin/settings/staff",
  );
  const publicPage = await proxy(
    new NextRequest("http://localhost/login", { headers: { "x-cardvert-admin-path": "/admin" } }),
  );
  expect(publicPage.headers.get("x-middleware-request-x-cardvert-admin-path")).toBeNull();
});
