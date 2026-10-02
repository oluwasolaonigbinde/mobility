import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), guard: vi.fn(), shell: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.guard }));
vi.mock("./global-search", () => ({ GlobalSearch: () => <p>Global search</p> }));
vi.mock("@/components/shell/app-shell", () => ({
  AppShell: (props: Record<string, unknown>) => {
    mocks.shell(props);
    return <div>{props.children as React.ReactNode}</div>;
  },
}));
import AdminLayout from "./layout";
beforeEach(() => {
  vi.clearAllMocks();
  mocks.guard.mockResolvedValue({ user: { full_name: "Terrax staff" } });
});
it("provides only available A destinations and known core discovery counts", async () => {
  mocks.get.mockResolvedValue({ data: { total: 3 } });
  render(await AdminLayout({ children: <p>Hub content</p> }));
  expect(screen.getByText("Hub content")).toBeTruthy();
  const nav = mocks.shell.mock.calls[0]![0].nav;
  expect(nav.map((item: { label: string }) => item.label)).toEqual([
    "Work queue",
    "Drivers",
    "Campaigns",
    "Advertisers",
    "Settings",
  ]);
  expect(nav[1].count).toBe(3);
  expect(nav[2].count).toBe(6);
  expect(nav[4].href).toBe("/admin/settings/staff");
  expect(mocks.get).toHaveBeenCalledTimes(3);
  expect(
    mocks.get.mock.calls.some(
      ([url]) => url.includes("fraud") || url.includes("payout") || url.includes("complaint"),
    ),
  ).toBe(false);
});
it("does not invent zero counts when the work lists are unavailable", async () => {
  mocks.get.mockRejectedValue(new Error("offline"));
  render(await AdminLayout({ children: null }));
  expect(
    mocks.shell.mock.calls[0]![0].nav.every((item: { count?: number }) => item.count === undefined),
  ).toBe(true);
});
it("does not read staff work before authorization", async () => {
  mocks.guard.mockRejectedValueOnce(new Error("denied"));
  await expect(AdminLayout({ children: null })).rejects.toThrow("denied");
  expect(mocks.get).not.toHaveBeenCalled();
});
