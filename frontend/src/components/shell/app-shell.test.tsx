import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { MeResponse } from "@/lib/auth/current-user";
import { AppShell } from "./app-shell";

vi.mock("@/components/notifications/notification-center", () => ({
  NotificationCenter: () => <div data-testid="notification-centre" />,
}));
vi.mock("@/components/auth/change-password-form", () => ({
  ChangePasswordForm: () => <form aria-label="Change password" />,
}));
vi.mock("@/lib/auth/actions", () => ({ signOutAction: vi.fn() }));

const me = {
  user: {
    id: "user-1",
    full_name: "Avery User",
    role: "advertiser",
  },
  advertiser_organization: {
    id: "org-1",
    name: "Acme",
    currency: "NGN",
    membership_role: "owner",
  },
} as MeResponse;

describe("AppShell account controls", () => {
  it("keeps password and durable sign-out actions reachable in the mobile shell", async () => {
    const user = userEvent.setup();
    render(
      <AppShell me={me} nav={[]}>
        <p>Advertiser content</p>
      </AppShell>,
    );

    await user.click(screen.getByText("Account"));
    const accountControls = screen.getByRole("region", { name: "Account" });
    expect(accountControls.closest("details")).toHaveClass("md:hidden");
    expect(within(accountControls).getByRole("form", { name: "Change password" })).toBeVisible();
    expect(within(accountControls).getByRole("button", { name: "Sign out" })).toBeEnabled();
  });
});
