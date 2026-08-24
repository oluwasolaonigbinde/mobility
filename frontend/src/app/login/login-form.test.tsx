import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LoginForm } from "./login-form";

vi.mock("./actions", () => ({
  demoLoginAction: vi.fn(),
  loginAction: vi.fn(),
}));

describe("LoginForm", () => {
  it("shows credential fields when demo login is disabled", () => {
    render(<LoginForm />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it.each(["advertiser", "driver", "admin"] as const)(
    "shows one-click access without credential fields for %s",
    (demoLoginRole) => {
      render(<LoginForm demoLoginRole={demoLoginRole} />);

      expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/demo/i);
    },
  );
});
