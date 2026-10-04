import { isValidElement, type ReactElement, type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  guard: vi.fn(),
  shell: vi.fn(),
  readWorkQueue: vi.fn(),
  waitingCounts: vi.fn(),
}));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.guard }));
vi.mock("./global-search", () => ({ GlobalSearch: () => <p>Global search</p> }));
vi.mock("./work-queue", () => ({
  readWorkQueue: mocks.readWorkQueue,
  waitingCounts: mocks.waitingCounts,
}));
vi.mock("@/components/shell/app-shell", () => ({
  AppShell: (props: Record<string, unknown>) => {
    mocks.shell(props);
    return <div>{props.children as ReactNode}</div>;
  },
}));
import AdminLayout from "./layout";

type NavItem = { label: string; href: string; badge?: ReactNode };

async function navFor() {
  render(await AdminLayout({ children: <p>Hub content</p> }));
  return mocks.shell.mock.calls[0]![0].nav as NavItem[];
}

/** Resolves the streamed badge (Suspense > async WaitingBadge) for one menu item. */
async function renderBadge(item: NavItem) {
  const suspense = item.badge as ReactElement<{ children: ReactElement }>;
  const badge = suspense.props.children as ReactElement<Record<string, unknown>>;
  const resolve = badge.type as (props: Record<string, unknown>) => Promise<ReactNode>;
  const output = await resolve(badge.props);
  return isValidElement(output) ? render(output).container : null;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.guard.mockResolvedValue({ user: { full_name: "Terrax staff" } });
  mocks.readWorkQueue.mockResolvedValue({});
});

it("provides the eight approved menu items with waiting badges on work areas", async () => {
  const nav = await navFor();
  expect(screen.getByText("Hub content")).toBeTruthy();
  expect(nav.map((item) => item.label)).toEqual([
    "Work queue",
    "Drivers",
    "Campaigns",
    "Advertisers",
    "Trip checks",
    "Money",
    "Support",
    "Settings",
  ]);
  expect(nav.filter((item) => item.badge === undefined).map((item) => item.label)).toEqual([
    "Advertisers",
    "Settings",
  ]);
  expect(nav[7]!.href).toBe("/admin/settings/staff");
});

it("shows a known waiting count on the menu badge", async () => {
  mocks.waitingCounts.mockReturnValue({ drivers: 3 });
  const nav = await navFor();
  const badge = await renderBadge(nav.find((item) => item.label === "Drivers")!);
  expect(badge).toHaveTextContent("3");
  expect(badge?.querySelector('[aria-label="3 waiting"]')).not.toBeNull();
});

it("shows no badge for zero waiting or when the work lists are unavailable", async () => {
  mocks.waitingCounts.mockReturnValue({ drivers: 0, campaigns: undefined });
  const nav = await navFor();
  expect(await renderBadge(nav.find((item) => item.label === "Drivers")!)).toBeNull();
  expect(await renderBadge(nav.find((item) => item.label === "Campaigns")!)).toBeNull();
});

it("does not read staff work before authorization", async () => {
  mocks.guard.mockRejectedValueOnce(new Error("denied"));
  await expect(AdminLayout({ children: null })).rejects.toThrow("denied");
  expect(mocks.readWorkQueue).not.toHaveBeenCalled();
});
