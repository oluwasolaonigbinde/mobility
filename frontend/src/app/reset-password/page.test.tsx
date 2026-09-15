import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const completePasswordResetAction = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ completePasswordResetAction }));

import ResetPasswordPage from "./page";

const props = (token?: string | string[]) => ({
  searchParams: Promise.resolve(token === undefined ? {} : { token }),
});

describe("password reset completion page", () => {
  beforeEach(() => completePasswordResetAction.mockReset());

  it("refuses a missing, repeated or oversized token without showing the form", async () => {
    for (const token of [undefined, ["a", "b"], "x".repeat(513)]) {
      const { unmount } = render(await ResetPasswordPage(props(token)));
      expect(screen.getByRole("alert")).toHaveTextContent("This reset link is incomplete");
      expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute(
        "href",
        "/forgot-password",
      );
      expect(screen.queryByLabelText("New password")).toBeNull();
      unmount();
    }
  });

  it("submits the token with both passwords and offers sign in after success", async () => {
    completePasswordResetAction.mockResolvedValue({
      done: "Your password has been reset. Sign in with your new password.",
    });
    const user = userEvent.setup();
    render(await ResetPasswordPage(props("reset-token")));
    await user.type(screen.getByLabelText("New password"), "a-new-long-password");
    await user.type(screen.getByLabelText("Confirm new password"), "a-new-long-password");
    await user.click(screen.getByRole("button", { name: "Reset password" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Your password has been reset");
    expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.queryByRole("button", { name: "Reset password" })).toBeNull();
    const sent = completePasswordResetAction.mock.calls[0]![1] as FormData;
    expect(sent.get("token")).toBe("reset-token");
    expect(sent.get("new_password")).toBe("a-new-long-password");
    expect(sent.get("confirm_password")).toBe("a-new-long-password");
  });

  it("keeps the form available after a refused reset", async () => {
    completePasswordResetAction.mockResolvedValue({
      error: "This reset link is invalid or has expired.",
    });
    render(await ResetPasswordPage(props("expired-token")));
    await userEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
