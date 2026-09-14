import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post }),
}));

import { completeDriverAccountSetupAction } from "./actions";

function setupForm(overrides: Record<string, string> = {}) {
  const form = new FormData();
  form.set("token", overrides.token ?? "one-use-setup-token");
  form.set("new_password", overrides.new_password ?? "replacement-password");
  form.set("confirm_password", overrides.confirm_password ?? "replacement-password");
  return form;
}

describe("completeDriverAccountSetupAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { message: "private service detail" } });
  });

  it("sets the password through the one-use setup authority without creating a session", async () => {
    await expect(completeDriverAccountSetupAction({}, setupForm())).resolves.toEqual({
      done: "Account setup completed. Sign in with your new password.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/driver-account-setup/complete", {
      body: {
        token: "one-use-setup-token",
        new_password: "replacement-password",
      },
    });
  });

  it("keeps expired, rejected, superseded, and replayed setup actions indistinguishable", async () => {
    mocks.post.mockRejectedValue(
      new ApiError(400, {
        code: "DRIVER_ACCOUNT_SETUP_INVALID",
        message: "application 42 was rejected and token row 7 was replayed",
      }),
    );

    const result = await completeDriverAccountSetupAction({}, setupForm());

    expect(result).toEqual({
      error: "This setup action is invalid, expired, or already used.",
    });
    expect(JSON.stringify(result)).not.toContain("application 42");
    expect(JSON.stringify(result)).not.toContain("token row 7");
  });

  it("rejects mismatched passwords without spending the setup authority", async () => {
    await expect(
      completeDriverAccountSetupAction({}, setupForm({ confirm_password: "different-password" })),
    ).resolves.toEqual({ error: "Passwords do not match" });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
