import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AppShell, type NavItem } from "@/components/shell/app-shell";

const nav: NavItem[] = [{ href: "/driver", label: "Home", exact: true }];

export default async function DriverLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("driver");
  return (
    <AppShell me={me} nav={nav}>
      {children}
    </AppShell>
  );
}
