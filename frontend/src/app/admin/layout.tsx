import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";
import { GlobalSearch } from "./global-search";
import { readWorkQueue, waitingCounts } from "./work-queue";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  const counts = waitingCounts(await readWorkQueue());
  const nav: NavItem[] = [
    { href: "/admin", label: "Work queue", exact: true, count: counts.total },
    { href: "/admin/drivers", label: "Drivers", count: counts.drivers },
    { href: "/admin/campaigns", label: "Campaigns", count: counts.campaigns },
    { href: "/admin/advertisers", label: "Advertisers" },
    { href: "/admin/trip-checks", label: "Trip checks", count: counts.trips },
    { href: "/admin/money", label: "Money", count: counts.money },
    { href: "/admin/support", label: "Support", count: counts.support },
    { href: "/admin/settings/staff", label: "Settings" },
  ];
  return (
    <AppShell me={me} nav={nav} search={<GlobalSearch />}>
      {children}
    </AppShell>
  );
}
