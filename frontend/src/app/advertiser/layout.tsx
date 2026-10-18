import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth/current-user";
import { AdvertiserShell } from "@/components/shell/advertiser-shell";

export default async function AdvertiserLayout({ children }: { children: ReactNode }) {
  const me = await requireRole("advertiser");
  return <AdvertiserShell me={me}>{children}</AdvertiserShell>;
}
