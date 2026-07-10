import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";

const nav: NavItem[] = [{ href: "/admin", label: "Operations", exact: true }];

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("admin");
  return (
    <AppShell me={me} nav={nav}>
      {children}
    </AppShell>
  );
}
