import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { toLagosDatetimeLocal } from "@/lib/campaigns/schema";
import { statusLabel } from "@/lib/campaigns/status";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { Panel } from "@/components/ui/panel";
import { CampaignEditForm } from "./campaign-edit-form";

export const metadata: Metadata = { title: "Edit campaign" };

export default async function EditCampaignPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  await requireRole("advertiser");
  const api = createApiClient(await getSessionToken());
  const campaignHref = `/advertiser/campaigns/${campaignId}`;
  const result = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
  if (!result.available) {
    if (result.reason === "missing") notFound();
    return (
      <DataUnavailable
        title="Campaign unavailable"
        reason={result.reason}
        retryHref={`${campaignHref}/edit`}
      />
    );
  }
  const campaign = result.data;
  const editable = campaign.status === "draft" || campaign.status === "rejected";

  return (
    <div className="animate-rise mx-auto max-w-3xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/advertiser/campaigns" className="hover:text-muted">
          Campaigns
        </Link>{" "}
        /{" "}
        <Link href={campaignHref} className="hover:text-muted">
          {campaign.name}
        </Link>{" "}
        / <span className="text-muted">Edit details</span>
      </nav>
      <h1 className="font-display mb-6 text-3xl font-semibold tracking-tight">
        Edit campaign details
      </h1>
      <Panel className="p-6">
        {editable ? (
          <CampaignEditForm
            campaignId={campaign.id}
            currency={campaign.currency}
            defaults={{
              name: campaign.name,
              description: campaign.description ?? "",
              start_at: toLagosDatetimeLocal(campaign.start_at),
              end_at: toLagosDatetimeLocal(campaign.end_at),
              budget_amount: campaign.budget_amount ?? "",
              daily_budget_amount: campaign.daily_budget_amount ?? "",
            }}
          />
        ) : (
          <div className="flex flex-col gap-3 text-sm">
            <p>
              This campaign is {statusLabel[campaign.status].toLowerCase()}, so its details can no
              longer be edited here.
            </p>
            <p className="text-muted">
              Approved and running campaigns change through a reviewed change request on the
              campaign page.
            </p>
            <Link href={campaignHref} className="text-amber underline">
              Back to the campaign
            </Link>
          </div>
        )}
      </Panel>
    </div>
  );
}
