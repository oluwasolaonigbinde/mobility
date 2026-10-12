"use client";

import { usePathname } from "next/navigation";
import { ViewTabs } from "@/components/ui/tabs";

export function SettingsNav() {
  const pathname = usePathname();
  return (
    <ViewTabs
      label="Settings"
      items={[
        ["staff", "Staff logins"],
        ["reach", "Reach estimates"],
        ["audiences", "Retargeting audiences"],
        ["activity", "Activity log"],
        ["support-tools", "Support tools"],
      ].map(([path, label]) => ({
        href: `/admin/settings/${path}`,
        label,
        active:
          pathname === `/admin/settings/${path}` || pathname.startsWith(`/admin/settings/${path}/`),
      }))}
    />
  );
}
