import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { validateDriverSession } from "./driver-session";

const mocks = vi.hoisted(() => ({
  getSessionToken: vi.fn(),
  setSessionCookie: vi.fn(),
  tokenNeedsRefresh: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ GET: mocks.get, POST: mocks.post }),
}));
vi.mock("./session", () => ({
  getSessionToken: mocks.getSessionToken,
  setSessionCookie: mocks.setSessionCookie,
}));
vi.mock("./token", () => ({ tokenNeedsRefresh: mocks.tokenNeedsRefresh }));

describe("validateDriverSession", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSessionToken.mockResolvedValue("http-only-token");
    mocks.tokenNeedsRefresh.mockReturnValue(false);
    mocks.get.mockResolvedValue({ data: { user: { id: "driver-1", role: "driver" } } });
  });

  it("returns the server-verified driver identity without exposing the token", async () => {
    await expect(validateDriverSession()).resolves.toEqual({
      status: "valid",
      driverId: "driver-1",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("rotates only after backend validation and stores the new token httpOnly", async () => {
    mocks.tokenNeedsRefresh.mockReturnValue(true);
    mocks.post.mockResolvedValue({ data: { access_token: "rotated", expires_in: 3600 } });

    await expect(validateDriverSession()).resolves.toEqual({
      status: "valid",
      driverId: "driver-1",
    });

    expect(mocks.get.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.post.mock.invocationCallOrder[0]!,
    );
    expect(mocks.setSessionCookie).toHaveBeenCalledWith("rotated", 3600);
  });

  it("rejects missing, wrong-role and revoked sessions", async () => {
    mocks.getSessionToken.mockResolvedValueOnce(undefined);
    await expect(validateDriverSession()).resolves.toEqual({ status: "missing" });

    mocks.getSessionToken.mockResolvedValueOnce("token");
    mocks.get.mockResolvedValueOnce({ data: { user: { id: "admin-1", role: "admin" } } });
    await expect(validateDriverSession()).resolves.toEqual({ status: "wrong-role" });

    mocks.get.mockRejectedValueOnce(
      new ApiError(401, { code: "SESSION_REVOKED", message: "revoked" }),
    );
    await expect(validateDriverSession()).resolves.toEqual({ status: "revoked" });
  });

  it("distinguishes provider loss from revocation", async () => {
    mocks.get.mockRejectedValueOnce(new Error("network down"));
    await expect(validateDriverSession()).resolves.toEqual({ status: "unavailable" });
    expect(mocks.setSessionCookie).not.toHaveBeenCalled();
  });
});
