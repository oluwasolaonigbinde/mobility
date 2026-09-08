import { notFound } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { PageHeader } from "@/components/ui/page-header";
import { CampaignWizard } from "./wizard";

export const metadata: Metadata = { title: "New campaign" };

export default async function NewCampaignPage({
  searchParams,
}: {
  searchParams: Promise<{ campaignId?: string }>;
}) {
  const me = await requireRole("advertiser");
  const { campaignId } = await searchParams;
  let existingCampaign;
  if (campaignId !== undefined) {
    if (!z.uuid().safeParse(campaignId).success) notFound();
    try {
      const { data } = await createApiClient(await getSessionToken()).GET(
        "/api/v1/advertiser/campaigns/{campaign_id}",
        { params: { path: { campaign_id: campaignId } } },
      );
      if (!data) notFound();
      existingCampaign = { id: data.id, name: data.name };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) notFound();
      throw error;
    }
  }
  const currency = me.advertiser_organization?.currency ?? "NGN";

  return (
    <div className="animate-rise mx-auto max-w-4xl">
      <PageHeader
        title={existingCampaign ? `Add creatives to ${existingCampaign.name}` : "New campaign"}
        eyebrow={
          existingCampaign
            ? "Recover missing attachments on this campaign"
            : "Set the basics — targeting zones come next"
        }
      />
      <CampaignWizard currency={currency} existingCampaign={existingCampaign} />
    </div>
  );
}
