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

import DriverChangePasswordPage from "./page";

describe("forced driver password logout", () => {
  beforeEach(() => {
    mocks.getCurrentUser.mockResolvedValue({
      user: { role: "driver", must_change_password: true },
    });
  });

  it("keeps global sign out reachable before the password is changed", async () => {
    render(await DriverChangePasswordPage());
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });
});
