import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";

const nav: NavItem[] = [
  { href: "/advertiser", label: "Overview", exact: true },
  { href: "/advertiser/campaigns", label: "Campaigns" },
  { href: "/advertiser/planning-sources", label: "Planning sources" },
  { href: "/advertiser/billing", label: "Billing" },
  { href: "/advertiser/company", label: "Company" },
];

export default async function AdvertiserLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("advertiser");
  return (
    <AppShell me={me} nav={nav}>
      {children}
    </AppShell>
  );
}
