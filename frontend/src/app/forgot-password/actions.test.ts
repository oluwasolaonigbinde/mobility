import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("next/headers", () => ({ headers: vi.fn(async () => new Headers()) }));
vi.mock("@/lib/env", () => ({
  env: () => ({ LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: undefined }),
}));
vi.mock("@/lib/api/client", () => ({
  createLoginApiClient: () => ({ POST: mocks.post }),
}));

import { requestPasswordResetAction } from "./actions";

describe("requestPasswordResetAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { message: "backend wording" } });
  });

  it("returns the same generic success and preserves normalized input", async () => {
    const form = new FormData();
    form.set("email", " Driver@Example.com ");
    await expect(requestPasswordResetAction({}, form)).resolves.toEqual({
      done: "If the account can be recovered, reset instructions will be sent.",
      email: "driver@example.com",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/password-reset/request", {
      body: { email: "driver@example.com" },
    });
  });

  it("never exposes backend error text", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(500, { code: "INTERNAL", message: "smtp provider secret.internal" }),
    );
    const form = new FormData();
    form.set("email", "driver@example.com");
    const result = await requestPasswordResetAction({}, form);
    expect(result.email).toBe("driver@example.com");
    expect(result.error).not.toContain("smtp");
    expect(result.error).not.toContain("secret.internal");
  });
});
