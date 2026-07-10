import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { PageHeader } from "@/components/ui/page-header";
import { CampaignWizard } from "./wizard";

export const metadata: Metadata = { title: "New campaign" };

export default async function NewCampaignPage() {
  const me = await requireRole("advertiser");
  const currency = me.advertiser_organization?.currency ?? "NGN";

  return (
    <div className="animate-rise mx-auto max-w-4xl">
      <PageHeader title="New campaign" eyebrow="Set the basics — targeting zones come next" />
      <CampaignWizard currency={currency} />
    </div>
  );
}
