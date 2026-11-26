import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const completePasswordResetAction = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ completePasswordResetAction }));

// REQ-316 F8: reset links carry the token in the fragment, captured on the client, so each
// test opens the page at a URL and loads fresh page-memory state.
async function openPage(url: string) {
  window.history.replaceState(null, "", url);
  vi.resetModules();
  return (await import("./page")).default;
}

describe("password reset completion page", () => {
  beforeEach(() => completePasswordResetAction.mockReset());

  it("refuses a missing, repeated, empty or oversized token without showing the form", async () => {
    for (const url of [
      "/reset-password",
      "/reset-password#token=a&token=b",
      "/reset-password#token=",
      `/reset-password#token=${"x".repeat(513)}`,
      "/reset-password?token=query-token",
    ]) {
      const ResetPasswordPage = await openPage(url);
      const { unmount } = render(<ResetPasswordPage />);
      expect(await screen.findByRole("alert")).toHaveTextContent("This reset link is incomplete");
      expect(screen.getByRole("link", { name: "Request a new link" })).toHaveAttribute(
        "href",
        "/forgot-password",
      );
      expect(screen.queryByLabelText("New password")).toBeNull();
      unmount();
    }
  });

  it("renders a neutral loading state on the server, never the incomplete-link alert", async () => {
    const ResetPasswordPage = await openPage("/reset-password#token=reset-token");
    const html = renderToString(<ResetPasswordPage />);
    expect(html).toContain("Opening your reset link");
    expect(html).not.toContain("incomplete");
    expect(html).not.toContain("reset-token");
  });

  it("hydrates from loading straight to the form without flashing the incomplete alert", async () => {
    const ResetPasswordPage = await openPage("/reset-password");
    const container = document.createElement("div");
    container.innerHTML = renderToString(<ResetPasswordPage />);
    document.body.append(container);
    const seen: string[] = [];
    const observer = new MutationObserver(() => seen.push(container.textContent ?? ""));
    observer.observe(container, { childList: true, subtree: true, characterData: true });
    window.history.replaceState(null, "", "/reset-password#token=reset-token");
    await act(async () => {
      hydrateRoot(container, <ResetPasswordPage />);
    });
    observer.disconnect();
    expect(window.location.hash).toBe("");
    expect(container.querySelector("input[name=token]")).toHaveValue("reset-token");
    expect(seen.join("\n")).not.toContain("incomplete");
    container.remove();
  });

  it("submits the token with both passwords and offers sign in after success", async () => {
    completePasswordResetAction.mockResolvedValue({
      done: "Your password has been reset. Sign in with your new password.",
    });
    const user = userEvent.setup();
    const ResetPasswordPage = await openPage("/reset-password#token=reset-token");
    render(<ResetPasswordPage />);
    expect(window.location.hash).toBe("");
    await user.type(await screen.findByLabelText("New password"), "a-new-long-password");
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
      requestNewLink: true,
    });
    const ResetPasswordPage = await openPage("/reset-password#token=expired-token");
    render(<ResetPasswordPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Reset password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
    expect(screen.getByRole("link", { name: "Send a new link" })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

it("keeps password-validation errors editable without suggesting a new link", async () => {
  completePasswordResetAction.mockResolvedValue({ error: "The passwords don't match." });
  const ResetPasswordPage = await openPage("/reset-password#token=valid-token");
  render(<ResetPasswordPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Reset password" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The passwords don't match.");
  expect(screen.queryByRole("link", { name: "Send a new link" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reset password" })).toBeEnabled();
});
