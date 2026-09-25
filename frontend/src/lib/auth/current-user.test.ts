import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: vi.fn() }));

import { isAdvertiserViewer, type MeResponse } from "./current-user";

function me(membership_role?: string) {
  return {
    user: { role: "advertiser" },
    advertiser_organization: membership_role ? { membership_role } : null,
  } as unknown as MeResponse;
}

describe("isAdvertiserViewer", () => {
  it("is true only for an explicit viewer membership", () => {
    expect(isAdvertiserViewer(me("viewer"))).toBe(true);
    expect(isAdvertiserViewer(me("owner"))).toBe(false);
    expect(isAdvertiserViewer(me("manager"))).toBe(false);
    // Unknown or missing roles never hide controls; the backend still decides.
    expect(isAdvertiserViewer(me())).toBe(false);
  });
});
