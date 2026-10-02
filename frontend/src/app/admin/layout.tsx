import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { GlobalSearch } from "./global-search";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  const api = createApiClient(await getSessionToken());
  const counts = await Promise.allSettled([
    api.GET("/api/v1/admin/driver-applications", { params: { query: { limit: 1 } } }),
    api.GET("/api/v1/admin/campaigns/pending-review", { params: { query: { limit: 1 } } }),
    api.GET("/api/v1/admin/creatives/pending-review", { params: { query: { limit: 1 } } }),
  ]);
  const count = (index: number) => {
    const result = counts[index];
    return result?.status === "fulfilled" ? result.value.data?.total : undefined;
  };
  const campaignCount =
    count(1) !== undefined && count(2) !== undefined ? count(1)! + count(2)! : undefined;
  const nav: NavItem[] = [
    { href: "/admin", label: "Work queue", exact: true },
    { href: "/admin/drivers", label: "Drivers", count: count(0) },
    { href: "/admin/campaigns", label: "Campaigns", count: campaignCount },
    { href: "/admin/advertisers", label: "Advertisers" },
    { href: "/admin/settings/staff", label: "Settings" },
  ];
  return (
    <AppShell me={me} nav={nav} search={<GlobalSearch />}>
      {children}
    </AppShell>
  );
}
