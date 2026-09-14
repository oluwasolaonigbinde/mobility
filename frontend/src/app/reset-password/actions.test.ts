import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { completePasswordResetAction } from "./actions";

function resetForm() {
  const form = new FormData();
  form.set("token", "setup-token");
  form.set("new_password", "replacement-password");
  form.set("confirm_password", "replacement-password");
  return form;
}

describe("completePasswordResetAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { message: "done" } });
  });

  it("shows completion in place", async () => {
    await expect(completePasswordResetAction({}, resetForm())).resolves.toEqual({
      done: "Password reset completed. Sign in with your new password.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/password-reset/complete", {
      body: { token: "setup-token", new_password: "replacement-password" },
    });
  });

  it("maps replay or expiry without exposing backend text", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(400, {
        code: "PASSWORD_RESET_INVALID",
        message: "database token row 42 already used",
      }),
    );
    await expect(completePasswordResetAction({}, resetForm())).resolves.toEqual({
      error: "This reset link is invalid, expired, or already used.",
    });
  });
});
