import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import { AdvertiserShell } from "@/components/shell/advertiser-shell";
import type { MeResponse } from "@/lib/auth/current-user";
import DriverPortalLayout from "@/app/driver/(portal)/layout";

const mocks = vi.hoisted(() => ({ requireRole: vi.fn() }));

vi.mock("@/components/notifications/notification-center", () => ({
  NotificationCenter: ({
    canManageAdvertiserPreferences,
    compact,
  }: {
    canManageAdvertiserPreferences?: boolean;
    compact?: boolean;
  }) => (
    <div
      data-testid="notification-centre"
      data-compact={String(Boolean(compact))}
      data-can-manage-preferences={String(Boolean(canManageAdvertiserPreferences))}
    />
  ),
}));
vi.mock("@/lib/auth/actions", () => ({ signOutAction: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.requireRole }));
vi.mock("@/components/driver/tab-bar", () => ({ TabBar: () => <div /> }));
vi.mock("@/components/driver/sw-register", () => ({ ServiceWorkerRegister: () => null }));
vi.mock("@/components/shell/advertiser-navigation", () => ({
  AdvertiserNavigation: () => <nav />,
}));

function me(role: "admin" | "advertiser" | "driver", membershipRole?: "advertiser") {
  return {
    user: { full_name: "Avery User", role },
    advertiser_organization:
      role === "advertiser"
        ? { id: "org", name: "Acme", currency: "NGN", membership_role: membershipRole }
        : null,
  } as MeResponse;
}

describe("notification shell placement", () => {
  it("mounts the common centre in both standard role shells", () => {
    const { rerender } = render(
      <AppShell me={me("admin")} nav={[]}>
        <p>Admin content</p>
      </AppShell>,
    );
    expect(screen.getByTestId("notification-centre")).toHaveAttribute(
      "data-can-manage-preferences",
      "false",
    );
    expect(screen.getByTestId("notification-centre")).toHaveAttribute("data-compact", "false");

    rerender(
      <AdvertiserShell me={me("advertiser", "advertiser")}>
        <p>Advertiser content</p>
      </AdvertiserShell>,
    );
    expect(screen.getByTestId("notification-centre")).toHaveAttribute(
      "data-can-manage-preferences",
      "true",
    );
    expect(screen.getByTestId("notification-centre")).toHaveAttribute("data-compact", "true");
  });

  it("mounts the same centre in the driver portal without advertiser preferences", async () => {
    mocks.requireRole.mockResolvedValue(me("driver"));
    render(await DriverPortalLayout({ children: <p>Driver content</p> }));
    expect(screen.getByTestId("notification-centre")).toHaveAttribute("data-compact", "true");
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.getByTestId("notification-centre")).toHaveAttribute(
      "data-can-manage-preferences",
      "false",
    );
  });
});
