import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const requestPasswordResetAction = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ requestPasswordResetAction }));

import ForgotPasswordPage from "./page";

const genericResponse =
  "If an eligible account exists, reset instructions will be sent to its email address.";

describe("password reset request page", () => {
  beforeEach(() => requestPasswordResetAction.mockReset());

  it("explains the privacy-preserving response and links back to sign in", () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeTruthy();
    expect(screen.getByText(/the response is the same whether or not an eligible/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/login");
  });

  it("submits the email and shows only the generic confirmation", async () => {
    requestPasswordResetAction.mockResolvedValue({ done: genericResponse });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset instructions" }));
    expect(await screen.findByRole("status")).toHaveTextContent(genericResponse);
    expect(screen.queryByRole("alert")).toBeNull();
    expect((requestPasswordResetAction.mock.calls[0]![1] as FormData).get("email")).toBe(
      "ada@example.com",
    );
  });

  it("shows a validation refusal and keeps the entered email", async () => {
    requestPasswordResetAction.mockResolvedValue({
      error: "Enter a valid email address.",
      email: "not-an-email",
    });
    const user = userEvent.setup();
    render(<ForgotPasswordPage />);
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Send reset instructions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(screen.getByLabelText("Email")).toHaveValue("not-an-email");
    expect(screen.queryByRole("status")).toBeNull();
  });
});
