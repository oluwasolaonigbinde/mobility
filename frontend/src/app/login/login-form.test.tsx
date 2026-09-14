import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "./login-form";
import type { LoginState } from "./actions";

const actionState = vi.hoisted(() => ({ state: {} as LoginState, pending: false }));
vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useActionState: () => [actionState.state, () => undefined, actionState.pending],
}));

vi.mock("./actions", () => ({
  demoLoginAction: vi.fn(),
  loginAction: vi.fn(),
}));

describe("LoginForm", () => {
  beforeEach(() => {
    actionState.state = {};
    actionState.pending = false;
  });
  it("shows credential fields when demo login is disabled", () => {
    render(<LoginForm />);

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it.each(["advertiser", "driver", "admin"] as const)(
    "shows one-click access without credential fields for %s",
    (demoLoginRole) => {
      render(<LoginForm demoLoginRole={demoLoginRole} />);

      expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/demo|synthetic/i);
    },
  );

  it.each([undefined, "advertiser"] as const)(
    "keeps sign-in errors and pending state visible for %s",
    (demoLoginRole) => {
      actionState.state = {
        error: "Could not sign in.",
        fieldErrors: { email: "Enter email", password: "Enter password" },
      };
      actionState.pending = true;
      render(<LoginForm demoLoginRole={demoLoginRole} />);
      expect(screen.getByText("Could not sign in.")).toHaveAttribute("role", "alert");
      expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
      if (!demoLoginRole) {
        expect(screen.getByText("Enter email")).toBeInTheDocument();
        expect(screen.getByText("Enter password")).toBeInTheDocument();
      }
    },
  );
});
