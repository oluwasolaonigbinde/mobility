import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/shell/app-shell";
import type { MeResponse } from "@/lib/auth/current-user";
import DriverPortalLayout from "@/app/driver/(portal)/layout";

const mocks = vi.hoisted(() => ({ requireRole: vi.fn() }));

vi.mock("@/components/notifications/notification-center", () => ({
  NotificationCenter: ({
    canManageAdvertiserPreferences,
  }: {
    canManageAdvertiserPreferences?: boolean;
  }) => (
    <div
      data-testid="notification-centre"
      data-can-manage-preferences={String(Boolean(canManageAdvertiserPreferences))}
    />
  ),
}));
vi.mock("@/lib/auth/actions", () => ({ signOutAction: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.requireRole }));
vi.mock("@/components/driver/tab-bar", () => ({ TabBar: () => <div /> }));
vi.mock("@/components/driver/sw-register", () => ({ ServiceWorkerRegister: () => null }));

function me(role: "admin" | "advertiser" | "driver", membershipRole?: "owner" | "viewer") {
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

    rerender(
      <AppShell me={me("advertiser", "owner")} nav={[]}>
        <p>Advertiser content</p>
      </AppShell>,
    );
    expect(screen.getByTestId("notification-centre")).toHaveAttribute(
      "data-can-manage-preferences",
      "true",
    );
  });

  it("mounts the same centre in the driver portal without advertiser preferences", async () => {
    mocks.requireRole.mockResolvedValue(me("driver"));
    render(await DriverPortalLayout({ children: <p>Driver content</p> }));
    expect(screen.getByTestId("notification-centre")).toHaveAttribute(
      "data-can-manage-preferences",
      "false",
    );
  });
});
