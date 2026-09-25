import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";

const nav: NavItem[] = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/users", label: "Users", group: "People & cars" },
  { href: "/admin/drivers", label: "Drivers", group: "People & cars" },
  { href: "/admin/driver-applications", label: "Driver applications", group: "People & cars" },
  { href: "/admin/vehicles", label: "Vehicles", group: "People & cars" },
  { href: "/admin/contact", label: "Driver contact", group: "People & cars" },
  { href: "/admin/approvals", label: "Approvals", group: "Campaigns" },
  { href: "/admin/assignments", label: "Assignments", group: "Campaigns" },
  { href: "/admin/planning-sources", label: "Planning sources", group: "Campaigns" },
  { href: "/admin/fraud", label: "Fraud", group: "Trips & money" },
  { href: "/admin/late-data", label: "Late trip evidence", group: "Trips & money" },
  { href: "/admin/payouts", label: "Payouts", group: "Trips & money" },
  { href: "/admin/billing", label: "Billing", group: "Trips & money" },
  { href: "/admin/measurement", label: "Measurement & reports", group: "Reports & records" },
  { href: "/admin/traffic", label: "Traffic", group: "Reports & records" },
  { href: "/admin/audit", label: "Audit", group: "Reports & records" },
];

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  return (
    <AppShell me={me} nav={nav}>
      {children}
    </AppShell>
  );
}
