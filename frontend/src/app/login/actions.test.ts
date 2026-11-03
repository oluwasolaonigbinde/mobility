import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  env: vi.fn(),
  post: vi.fn(),
  setSessionCookie: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
}));

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: mocks.redirect,
}));
vi.mock("next/headers", () => ({ headers: vi.fn(async () => new Headers()) }));
vi.mock("@/lib/env", () => ({ env: mocks.env }));
vi.mock("@/lib/auth/session", () => ({ setSessionCookie: mocks.setSessionCookie }));
vi.mock("@/lib/api/client", () => ({
  createLoginApiClient: () => ({ POST: mocks.post }),
}));

import { demoLoginAction } from "./actions";
import { loginAction } from "./actions";
import { ApiError } from "@/lib/api/errors";

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

  it("forwards the same-role return through demo sign-in", async () => {
    const form = new FormData();
    form.set("from", "/admin/campaigns/123");
    await expect(demoLoginAction("admin", {}, form)).rejects.toThrow(
      "redirect:/admin/campaigns/123",
    );
  });
});

describe("loginAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.env.mockReturnValue({ LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: false });
  });

  it.each([
    ["admin", "/admin/campaigns/123", "/admin/campaigns/123"],
    ["advertiser", "/advertiser/billing", "/advertiser/billing"],
    ["driver", "/driver/jobs", "/driver/jobs"],
    ["admin", "/driver/jobs", "/admin"],
    ["advertiser", "/admin", "/advertiser"],
    ["driver", "/advertiser", "/driver"],
    ["admin", "https://example.test/admin", "/admin"],
    ["admin", "//example.test/admin", "/admin"],
    ["admin", "/adminfoo", "/admin"],
    ["admin", "/adminfoo/jobs", "/admin"],
    ["admin", "/admin/%2f%2Fexample.test", "/admin"],
    ["admin", "/admin/%5cdriver", "/admin"],
    ["admin", "/admin/%5Cdriver", "/admin"],
    ["admin", "/admin/%2e%2e/driver", "/admin"],
    ["admin", "/admin/%2E%2E/driver", "/admin"],
    ["admin", "/admin/%252fexample.test", "/admin"],
    ["admin", "/admin/../driver", "/admin"],
    ["admin", "/admin/\\driver", "/admin"],
  ])("returns %s safely from %s", async (role, from, destination) => {
    mocks.post.mockResolvedValue({
      data: { access_token: "token", expires_in: 3600, user: { role } },
    });
    const form = new FormData();
    form.set("email", "person@example.test");
    form.set("password", "password");
    form.set("from", from);
    await expect(loginAction({}, form)).rejects.toThrow(`redirect:${destination}`);
  });

  it("requires a password change before following a valid return", async () => {
    mocks.post.mockResolvedValue({
      data: {
        access_token: "token",
        expires_in: 3600,
        user: { role: "admin", must_change_password: true },
      },
    });
    const form = new FormData();
    form.set("email", "person@example.test");
    form.set("password", "password");
    form.set("from", "/admin/campaigns/123");
    await expect(loginAction({}, form)).rejects.toThrow("redirect:/change-password");
  });

  it("does not expose an unexpected backend message", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(500, {
        code: "INTERNAL_ERROR",
        message: "database topology and private request details",
      }),
    );
    const formData = new FormData();
    formData.set("email", "advertiser@example.com");
    formData.set("password", "valid-password");

    await expect(loginAction({}, formData)).resolves.toEqual({
      error: "Sign-in is temporarily unavailable. Please try again.",
    });
  });
});
