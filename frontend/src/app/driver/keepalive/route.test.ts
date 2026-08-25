import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

const auth = vi.hoisted(() => ({
  validateDriverSession: vi.fn(),
  clearSessionCookie: vi.fn(),
}));

vi.mock("@/lib/auth/driver-session", () => ({
  validateDriverSession: auth.validateDriverSession,
}));
vi.mock("@/lib/auth/session", () => ({
  clearSessionCookie: auth.clearSessionCookie,
}));

describe("driver keepalive", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("rejects and clears a revoked session instead of returning a blind 204", async () => {
    auth.validateDriverSession.mockResolvedValue({ status: "revoked" });

    const response = await GET();

    expect(response.status).toBe(401);
    expect(auth.clearSessionCookie).toHaveBeenCalledTimes(1);
  });

  it("returns only the validated driver identity for a valid cookie session", async () => {
    auth.validateDriverSession.mockResolvedValue({ status: "valid", driverId: "driver-1" });
    const response = await GET();
    await expect(response.json()).resolves.toEqual({ status: "valid", driverId: "driver-1" });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(auth.clearSessionCookie).not.toHaveBeenCalled();
  });

  it("retains the cookie on provider loss but clears wrong-role sessions", async () => {
    auth.validateDriverSession.mockResolvedValueOnce({ status: "unavailable" });
    expect((await GET()).status).toBe(503);
    expect(auth.clearSessionCookie).not.toHaveBeenCalled();

    auth.validateDriverSession.mockResolvedValueOnce({ status: "wrong-role" });
    expect((await GET()).status).toBe(403);
    expect(auth.clearSessionCookie).toHaveBeenCalledTimes(1);
  });
});
