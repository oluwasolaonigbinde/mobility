import type { ReactNode } from "react";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { CampaignTabs } from "./campaign-tabs";

export default async function CampaignLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ campaignId: string }>;
}) {
  await requireRole("advertiser");
  const { campaignId } = await params;
  return (
    <div className="mx-auto max-w-6xl min-w-0">
      <Link
        href="/advertiser/campaigns"
        className="text-muted hover:text-green mb-5 inline-block text-sm"
      >
        ← All campaigns
      </Link>
      <CampaignTabs campaignId={campaignId} />
      {children}
    </div>
  );
}
