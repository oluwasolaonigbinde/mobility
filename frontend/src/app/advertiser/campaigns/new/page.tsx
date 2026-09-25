import { notFound } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import type { Metadata } from "next";
import Link from "next/link";
import { isAdvertiserViewer, requireRole } from "@/lib/auth/current-user";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { CampaignWizard } from "./wizard";

export const metadata: Metadata = { title: "New campaign" };

export default async function NewCampaignPage({
  searchParams,
}: {
  searchParams: Promise<{ campaignId?: string; requestId?: string }>;
}) {
  const me = await requireRole("advertiser");
  if (isAdvertiserViewer(me)) {
    return (
      <div className="animate-rise mx-auto max-w-4xl">
        <PageHeader title="New campaign" eyebrow="View-only access" />
        <Panel className="p-5 text-sm">
          <p>Only company owners and managers can create campaigns or add creatives.</p>
          <p className="text-muted mt-1">
            Ask one of them to do it, or to change your access.{" "}
            <Link href="/advertiser/campaigns" className="text-amber hover:underline">
              Back to campaigns
            </Link>
          </p>
        </Panel>
      </div>
    );
  }
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
            ? "Upload creatives and attach them to this campaign"
            : "Set the basics, then add creatives — campaign areas are set on the campaign page"
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
