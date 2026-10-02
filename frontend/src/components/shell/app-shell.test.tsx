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
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/settings/staff" }));

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

  it("groups the desktop sidebar and lets it scroll so sign-out stays reachable", () => {
    render(
      <AppShell
        me={me}
        nav={[
          { href: "/admin", label: "Overview", exact: true },
          { href: "/admin/settings/staff", label: "Users", group: "People & cars" },
          { href: "/admin/drivers", label: "Drivers", group: "People & cars" },
          { href: "/admin/money", label: "Payouts", group: "Trips & money" },
        ]}
      >
        <p>Admin content</p>
      </AppShell>,
    );

    const sidebar = document.querySelector("aside")!;
    const nav = within(sidebar).getByRole("navigation", { name: "Primary" });
    expect(nav).toHaveClass("overflow-y-auto", "min-h-0");
    expect(within(nav).getAllByText("People & cars")).toHaveLength(1);
    expect(within(nav).getByText("Trips & money")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Users" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const mobileNav = document.querySelector("header ~ nav")!;
    expect(mobileNav).not.toHaveTextContent("People & cars");
  });
});
