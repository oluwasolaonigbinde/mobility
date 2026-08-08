import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

describe("server environment", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("accepts blank demo credentials while demo login is disabled", async () => {
    vi.stubEnv("DEMO_LOGIN_ENABLED", "false");
    vi.stubEnv("DEMO_LOGIN_ADVERTISER_EMAIL", "");
    vi.stubEnv("DEMO_LOGIN_ADVERTISER_PASSWORD", "");
    vi.stubEnv("DEMO_LOGIN_DRIVER_EMAIL", "");
    vi.stubEnv("DEMO_LOGIN_DRIVER_PASSWORD", "");
    vi.stubEnv("DEMO_LOGIN_ADMIN_EMAIL", "");
    vi.stubEnv("DEMO_LOGIN_ADMIN_PASSWORD", "");

    const { env } = await import("./env");

    expect(env()).toMatchObject({
      DEMO_LOGIN_ENABLED: false,
      DEMO_LOGIN_ADVERTISER_EMAIL: undefined,
      DEMO_LOGIN_ADVERTISER_PASSWORD: undefined,
      DEMO_LOGIN_DRIVER_EMAIL: undefined,
      DEMO_LOGIN_DRIVER_PASSWORD: undefined,
      DEMO_LOGIN_ADMIN_EMAIL: undefined,
      DEMO_LOGIN_ADMIN_PASSWORD: undefined,
    });
  });
});
