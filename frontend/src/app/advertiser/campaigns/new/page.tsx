import { notFound, redirect } from "next/navigation";
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
import { toLagosDatetimeLocal } from "@/lib/campaigns/schema";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import type { components } from "@/lib/api/schema";
import { loadCampaignAreas } from "@/lib/advertiser/campaign-visuals";

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
  let initialZones: components["schemas"]["CampaignZoneRead"][] = [];
  const api = createApiClient(await getSessionToken());
  const recoveryUnavailable = () => (
    <DataUnavailable
      title="Your saved draft couldn't be confirmed"
      reason="protocol"
      retryHref={`/advertiser/campaigns/new?${campaignId ? "campaignId" : "requestId"}=${campaignId ?? requestId}`}
    />
  );
  const recoveryId = campaignId ?? requestId;
  if (recoveryId !== undefined) {
    if (!z.uuid().safeParse(recoveryId).success) notFound();
    try {
      const { data } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
        params: { path: { campaign_id: recoveryId } },
      });
      if (!data || data.id !== recoveryId) return recoveryUnavailable();
      existingCampaign = {
        id: data.id,
        name: data.name,
        basics: {
          name: data.name,
          description: data.description ?? "",
          start_at: toLagosDatetimeLocal(data.start_at),
          end_at: toLagosDatetimeLocal(data.end_at),
          budget_amount: data.budget_amount ?? "",
          daily_budget_amount: data.daily_budget_amount ?? "",
        },
      };
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) redirect("/login");
      return recoveryUnavailable();
    }
    // Outside the try so its sign-in redirect is not swallowed.
    const zones = await loadCampaignAreas(api, recoveryId, true);
    if (!zones.available) return recoveryUnavailable();
    initialZones = zones.data.items;
  }
  const currency = me.advertiser_organization?.currency ?? "NGN";

  return (
    <div className="animate-rise mx-auto max-w-4xl">
      <PageHeader
        title={existingCampaign ? `Finish ${existingCampaign.name}` : "New campaign"}
        eyebrow={
          existingCampaign
            ? "Your draft is saved. Choose its areas and advert design."
            : "Start with the basics, then choose your areas and advert design"
        }
      />
      <CampaignWizard
        currency={currency}
        existingCampaign={existingCampaign}
        campaignRequestId={requestId}
        initialZones={initialZones}
      />
    </div>
  );
}
