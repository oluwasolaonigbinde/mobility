"use client";
import { usePathname } from "next/navigation";
import { ViewTabs } from "@/components/ui/tabs";

export function CampaignTabs({ campaignId }: { campaignId: string }) {
  const pathname = usePathname();
  const base = `/advertiser/campaigns/${campaignId}`;
  return (
    <ViewTabs
      label="Campaign pages"
      items={[
        ["", "Overview"],
        ["/report", "Results"],
        ["/map", "Map"],
        ["/zones", "Areas"],
        ["/invoices", "Invoices"],
      ].map(([path, label]) => ({
        href: base + path,
        label,
        active: path
          ? pathname === base + path || pathname.startsWith(`${base + path}/`)
          : pathname === base || pathname === `${base}/edit`,
      }))}
    />
  );
}
