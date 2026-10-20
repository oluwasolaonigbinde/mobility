import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ getCurrentUser: vi.fn() }));

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  getCurrentUser: mocks.getCurrentUser,
  roleHome: vi.fn(() => "/advertiser"),
}));
vi.mock("@/components/auth/change-password-form", () => ({
  ChangePasswordForm: () => <div>password form</div>,
}));

import ChangePasswordPage from "./page";

describe("forced password logout", () => {
  beforeEach(() => {
    mocks.getCurrentUser.mockResolvedValue({
      user: { role: "advertiser", must_change_password: true },
    });
  });

  it("keeps global sign out reachable before the password is changed", async () => {
    render(await ChangePasswordPage());
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
  it("also lets a signed-in advertiser change a non-temporary password", async () => {
    mocks.getCurrentUser.mockResolvedValue({
      user: { role: "advertiser", must_change_password: false },
    });
    render(await ChangePasswordPage());
    expect(screen.getByText("password form")).toBeVisible();
    expect(screen.getByRole("link", { name: "Back to Cardvert" })).toHaveAttribute(
      "href",
      "/advertiser",
    );
  });
});
