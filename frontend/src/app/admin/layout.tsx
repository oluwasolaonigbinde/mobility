import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";

const nav: NavItem[] = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/drivers", label: "Drivers" },
  { href: "/admin/vehicles", label: "Vehicles" },
  { href: "/admin/assignments", label: "Assignments" },
  { href: "/admin/fraud", label: "Fraud" },
  { href: "/admin/payouts", label: "Payouts" },
  { href: "/admin/billing", label: "Billing" },
  { href: "/admin/audit", label: "Audit" },
  { href: "/admin/traffic", label: "Traffic" },
];

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  return (
    <AppShell me={me} nav={nav}>
      {children}
    </AppShell>
  );
}
