import { Suspense, type ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";
import { GlobalSearch } from "./global-search";
import { createApiClient } from "@/lib/api/client";
import { readAdminBadgeSummary } from "@/lib/api/navigation";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { redirect } from "next/navigation";
import type { components } from "@/lib/api/schema";

type BadgeSummary = components["schemas"]["AdminBadgeSummary"];
type BadgeArea = "total" | "drivers" | "campaigns" | "trips" | "money" | "support";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  // One promise for this render; never a cross-user or cross-request cache.
  const counts = getSessionToken()
    .then((token) => readAdminBadgeSummary(createApiClient(token)))
    .then(({ data }) => data)
    .catch((error: unknown) => {
      if (error instanceof ApiError && [401, 403].includes(error.status)) redirect("/login");
      return undefined;
    });
  const badge = (area: BadgeArea) => (
    <Suspense fallback={null}>
      <WaitingBadge area={area} counts={counts} />
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

async function WaitingBadge({
  area,
  counts,
}: {
  area: BadgeArea;
  counts: Promise<BadgeSummary | undefined>;
}) {
  const count = (await counts)?.[area];
  if (count === undefined || !Number.isSafeInteger(count) || count < 0)
    return (
      <span className="text-muted ml-2" aria-label="Waiting count unavailable">
        —
      </span>
    );
  return count ? (
    <span
      className="bg-amber/15 text-amber ml-2 rounded-full px-2 py-0.5"
      aria-label={`${count} waiting`}
    >
      {count}
    </span>
  ) : null;
}
