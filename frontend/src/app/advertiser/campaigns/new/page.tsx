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
  searchParams: Promise<{ campaignId?: string; requestId?: string }>;
}) {
  const me = await requireRole("advertiser");
  const { campaignId, requestId } = await searchParams;
  if (requestId !== undefined && !z.uuid().safeParse(requestId).success) notFound();
  let existingCampaign;
  const recoveryId = campaignId ?? requestId;
  if (recoveryId !== undefined) {
    if (!z.uuid().safeParse(recoveryId).success) notFound();
    try {
      const { data } = await createApiClient(await getSessionToken()).GET(
        "/api/v1/advertiser/campaigns/{campaign_id}",
        { params: { path: { campaign_id: recoveryId } } },
      );
      if (data) existingCampaign = { id: data.id, name: data.name };
      else if (campaignId !== undefined) notFound();
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        if (campaignId !== undefined) notFound();
      } else {
        throw error;
      }
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
      <CampaignWizard
        currency={currency}
        existingCampaign={existingCampaign}
        campaignRequestId={requestId}
      />
    </div>
  );
}
