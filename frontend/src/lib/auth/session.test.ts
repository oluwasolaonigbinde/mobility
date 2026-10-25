// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextResponse } from "next/server";

const mocks = vi.hoisted(() => ({ cookies: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: mocks.cookies }));
vi.mock("@/lib/env", () => ({ env: () => ({ SESSION_COOKIE_NAME: "__Host-cardvert_session" }) }));
import { clearSessionCookie, setSessionCookie } from "./session";

afterEach(() => vi.unstubAllEnvs());

describe("production host-only session cookie", () => {
  it("serializes a matching Secure, Path=/ expiry header", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const response = new NextResponse();
    mocks.cookies.mockResolvedValue(response.cookies);
    await setSessionCookie("synthetic-session", 3600);
    expect(response.headers.get("set-cookie")).toContain(
      "__Host-cardvert_session=synthetic-session",
    );
    await clearSessionCookie();
    const header = response.headers.get("set-cookie")!;
    expect(header).toContain("__Host-cardvert_session=;");
    expect(header).toMatch(/; Secure(?:;|$)/i);
    expect(header).toContain("Path=/");
    expect(header).toContain("Max-Age=0");
    expect(header).toContain("Expires=Thu, 01 Jan 1970 00:00:00 GMT");
    expect(header).not.toMatch(/Domain=/i);
  });
});
