import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  env: vi.fn(),
  post: vi.fn(),
  setSessionCookie: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
}));

vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("next/headers", () => ({ headers: vi.fn(async () => new Headers()) }));
vi.mock("@/lib/env", () => ({ env: mocks.env }));
vi.mock("@/lib/auth/session", () => ({ setSessionCookie: mocks.setSessionCookie }));
vi.mock("@/lib/api/client", () => ({
  createLoginApiClient: () => ({ POST: mocks.post }),
}));

import { demoLoginAction } from "./actions";

const roleCredentials = {
  advertiser: ["advertiser@example.com", "advertiser-password"],
  driver: ["driver@example.com", "driver-password"],
  admin: ["admin@example.com", "admin-password"],
} as const;

describe("demoLoginAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.env.mockReturnValue({
      DEMO_LOGIN_ENABLED: true,
      DEMO_LOGIN_ADVERTISER_EMAIL: roleCredentials.advertiser[0],
      DEMO_LOGIN_ADVERTISER_PASSWORD: roleCredentials.advertiser[1],
      DEMO_LOGIN_DRIVER_EMAIL: roleCredentials.driver[0],
      DEMO_LOGIN_DRIVER_PASSWORD: roleCredentials.driver[1],
      DEMO_LOGIN_ADMIN_EMAIL: roleCredentials.admin[0],
      DEMO_LOGIN_ADMIN_PASSWORD: roleCredentials.admin[1],
      LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: false,
    });
    mocks.post.mockImplementation(async (_path: string, request: { body: unknown }) => ({
      data: {
        access_token: "token",
        expires_in: 3600,
        user: { role: (request.body as { email: string }).email.split("@")[0] },
      },
    }));
  });

  it.each(["advertiser", "driver", "admin"] as const)(
    "uses only the configured %s credentials",
    async (role) => {
      await expect(demoLoginAction(role, {}, new FormData())).rejects.toThrow(`redirect:/${role}`);

      expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/login", {
        body: { email: roleCredentials[role][0], password: roleCredentials[role][1] },
      });
    },
  );

  it("fails closed when the selected role credentials are missing", async () => {
    mocks.env.mockReturnValue({
      ...mocks.env(),
      DEMO_LOGIN_ADMIN_EMAIL: undefined,
      DEMO_LOGIN_ADMIN_PASSWORD: undefined,
    });

    await expect(demoLoginAction("admin", {}, new FormData())).resolves.toEqual({
      error: "Sign-in is unavailable.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
