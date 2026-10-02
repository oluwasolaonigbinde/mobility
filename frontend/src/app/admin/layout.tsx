import { Suspense, type ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";
import { GlobalSearch } from "./global-search";
import { readWorkQueue, waitingCounts } from "./work-queue";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  const badge = (area: keyof ReturnType<typeof waitingCounts>) => (
    <Suspense fallback={null}>
      <WaitingBadge area={area} />
    </Suspense>
  );
  const nav: NavItem[] = [
    { href: "/admin", label: "Work queue", exact: true, badge: badge("total") },
    { href: "/admin/drivers", label: "Drivers", badge: badge("drivers") },
    { href: "/admin/campaigns", label: "Campaigns", badge: badge("campaigns") },
    { href: "/admin/advertisers", label: "Advertisers" },
    { href: "/admin/trip-checks", label: "Trip checks", badge: badge("trips") },
    { href: "/admin/money", label: "Money", badge: badge("money") },
    { href: "/admin/support", label: "Support", badge: badge("support") },
    { href: "/admin/settings/staff", label: "Settings" },
  ];
  return (
    <AppShell me={me} nav={nav} search={<GlobalSearch />}>
      {children}
    </AppShell>
  );
}

async function WaitingBadge({ area }: { area: keyof ReturnType<typeof waitingCounts> }) {
  const count = waitingCounts(await readWorkQueue())[area];
  return count ? (
    <span
      className="bg-amber/15 text-amber ml-2 rounded-full px-2 py-0.5"
      aria-label={`${count} waiting`}
    >
      {count}
    </span>
  ) : null;
}
