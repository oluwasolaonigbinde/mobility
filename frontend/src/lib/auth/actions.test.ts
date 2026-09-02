import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  clearSessionCookie: vi.fn(),
  getSessionToken: vi.fn(),
}));

vi.mock("@/lib/env", () => ({ env: () => ({ API_BASE_URL: "http://api:8000" }) }));
vi.mock("./session", () => ({
  clearSessionCookie: mocks.clearSessionCookie,
  getSessionToken: mocks.getSessionToken,
}));

import { signOutAction } from "./actions";

describe("global sign out action", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("revokes the backend session before clearing the current cookie", async () => {
    mocks.getSessionToken.mockResolvedValue("current-bearer");
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetch);

    await expect(signOutAction()).resolves.toEqual({
      globalRevocationConfirmed: true,
      globalRevocationFailed: false,
    });

    expect(fetch).toHaveBeenCalledWith("http://api:8000/api/v1/auth/logout", {
      method: "POST",
      headers: { Authorization: "Bearer current-bearer" },
      cache: "no-store",
    });
    expect(mocks.clearSessionCookie).toHaveBeenCalledOnce();
  });

  it("clears an already-invalid local session without claiming backend success", async () => {
    mocks.getSessionToken.mockResolvedValue("revoked-bearer");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

    await expect(signOutAction()).resolves.toEqual({
      globalRevocationConfirmed: false,
      globalRevocationFailed: false,
    });

    expect(mocks.clearSessionCookie).toHaveBeenCalledOnce();
  });

  it("keeps the local session and surfaces a backend outage", async () => {
    mocks.getSessionToken.mockResolvedValue("current-bearer");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    await expect(signOutAction()).resolves.toEqual({
      globalRevocationConfirmed: false,
      globalRevocationFailed: true,
    });
    expect(mocks.clearSessionCookie).not.toHaveBeenCalled();
  });
});
