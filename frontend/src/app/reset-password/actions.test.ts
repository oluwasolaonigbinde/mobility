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
      requestNewLink: true,
    });
  });
});

it("uses invite wording and its own completion endpoint, without an automatic sign-in", async () => {
  mocks.post.mockResolvedValue({ data: { message: "done" } });
  const { completeAdvertiserInviteAction } = await import("./actions");
  expect(await completeAdvertiserInviteAction({}, resetForm())).toEqual({
    done: "Your login is ready. Sign in with your new password.",
  });
  expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/auth/advertiser-invite/complete", {
    body: { token: "setup-token", new_password: "replacement-password" },
  });
  mocks.post.mockRejectedValueOnce(
    new ApiError(400, { code: "ADVERTISER_INVITE_INVALID", message: "private token details" }),
  );
  expect(await completeAdvertiserInviteAction({}, resetForm())).toEqual({
    error: "This invite link is invalid, expired, or already used. Ask Terrax for a new invite.",
  });
});

it.each(["short", "mismatch", "server-short"])(
  "does not recommend replacing the link for %s password errors",
  async (kind) => {
    mocks.post.mockReset();
    const form = resetForm();
    if (kind === "short") {
      form.set("new_password", "short");
      form.set("confirm_password", "short");
    } else if (kind === "mismatch") form.set("confirm_password", "a different long password");
    else
      mocks.post.mockRejectedValueOnce(
        new ApiError(400, { code: "PASSWORD_TOO_SHORT", message: "private" }),
      );
    const result = await completePasswordResetAction({}, form);
    expect(result.error).toBeTruthy();
    expect(result.requestNewLink).toBeUndefined();
    if (kind !== "server-short") expect(mocks.post).not.toHaveBeenCalled();
  },
);
