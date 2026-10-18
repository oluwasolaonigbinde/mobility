import type { Metadata } from "next";
import { randomUUID } from "node:crypto";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { requireRole, isAdvertiserViewer } from "@/lib/auth/current-user";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { getSessionToken } from "@/lib/auth/session";
import { formatCount, formatDate, formatDateRange, formatMoney } from "@/lib/format";
import { statusLabel } from "@/lib/campaigns/status";
import { Panel } from "@/components/ui/panel";
import { CampaignArtwork } from "@/components/campaigns/campaign-artwork";
import { AreaGraphic } from "@/components/campaigns/area-graphic";
import { BudgetUsed } from "@/components/campaigns/budget-used";
import { loadCampaignVisuals, previewFile } from "@/lib/advertiser/campaign-visuals";
import { recordedBudget } from "@/lib/advertiser/budget-display";
import { isOutstandingInvoice } from "@/lib/billing/commercial-history";
import { StatusActions } from "./status-actions";
import { CommercialPanel } from "./commercial-panel";
import { CreativeStatusActions } from "./creative-status-actions";
import { CampaignChangePanel } from "./campaign-change-panel";
import { CampaignCancellationPanel } from "./campaign-cancellation-panel";

export const metadata: Metadata = { title: "Campaign" };
const sentences: Record<string, string> = {
  draft: "Let’s get your campaign ready for the road.",
  pending_review: "Terrax Media is reviewing your campaign.",
  rejected: "Terrax Media has asked for a few changes.",
  approved: "Your campaign is approved. Terrax Media is arranging the next steps.",
  scheduled: "Your campaign is ready for its start date.",
  active: "Your campaign is running. Your brand is out on the road.",
  paused: "Your campaign is paused. Contact Terrax Media about the next steps.",
  completed: "Your campaign has finished.",
  cancelled: "This campaign has been cancelled.",
};

export default async function CampaignDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<{ commercial_error?: string; details?: string; manage?: string }>;
}) {
  const { campaignId } = await params;
  const query = await searchParams;
  const me = await requireRole("advertiser");
  const canWrite = !isAdvertiserViewer(me);
  const api = createApiClient(await getSessionToken());
  const base = `/advertiser/campaigns/${campaignId}`;
  const loaded = await loadAdvertiserPageData(() =>
    api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
      params: { path: { campaign_id: campaignId } },
    }),
  );
  if (!loaded.available) {
    if (loaded.reason === "missing") notFound();
    return <DataUnavailable title="Campaign unavailable" reason={loaded.reason} retryHref={base} />;
  }
  const campaign = loaded.data;
  const [visuals, commercial, summary, history, changes] = await Promise.all([
    loadCampaignVisuals(api, campaignId),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
        params: { path: { campaign_id: campaignId } },
      }),
    ),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/summary", {
        params: { path: { campaign_id: campaignId } },
      }),
    ),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/review-history", {
        params: { path: { campaign_id: campaignId } },
      }),
    ),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}/change-requests", {
        params: { path: { campaign_id: campaignId } },
      }),
    ),
  ]);
  const { artwork, areas } = visuals;
  const creativeItems = artwork.available ? artwork.data.items : [];
  const artworkReasons = new Map(
    await Promise.all(
      creativeItems
        .filter((item) => item.status === "rejected")
        .map(async (item) => {
          const result = await loadAdvertiserPageData(() =>
            api.GET(
              "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/review-history",
              {
                params: {
                  path: { campaign_id: campaignId, creative_id: item.id },
                  query: { limit: 1 },
                },
              },
            ),
          );
          return [
            item.id,
            result.available ? result.data.items[0]?.rejection_reason : undefined,
          ] as const;
        }),
    ),
  );
  const terminal = ["completed", "cancelled"].includes(campaign.status);
  const editable = ["draft", "rejected"].includes(campaign.status);
  const changeable = ["scheduled", "active", "paused"].includes(campaign.status);
  const invoice = commercial.available
    ? commercial.data.invoices?.find(isOutstandingInvoice)
    : undefined;
  let next = { label: "See results", href: `${base}/report` };
  if (campaign.status === "cancelled") next = { label: "View invoices", href: `${base}/invoices` };
  else if (campaign.status === "paused")
    next = { label: "Contact Terrax Media", href: "/advertiser/help" };
  else if (!canWrite && !terminal && campaign.status !== "active")
    next = invoice
      ? { label: "View invoice", href: `${base}/invoices/${invoice.id}` }
      : { label: "View campaign details", href: `${base}?details=campaign#details` };
  else if (!terminal && campaign.status !== "active") {
    if (editable && (!campaign.start_at || !campaign.end_at || !campaign.budget_amount))
      next = { label: "Add campaign details", href: `${base}/edit` };
    else if (editable && areas.available && areas.data.total === 0)
      next = { label: "Choose your area", href: `${base}/zones` };
    else if (!commercial.available || !artwork.available || (editable && !areas.available))
      next = { label: "Try again", href: base };
    else if (!commercial.data.terms)
      next = {
        label: commercial.data.revisions?.length ? "Review your quotation" : "View your quotation",
        href: `${base}?details=quotation#quotation`,
      };
    else if (
      !creativeItems.length ||
      creativeItems.some((item) => ["draft", "rejected"].includes(item.status))
    )
      next = {
        label: "Add or update artwork",
        href: `/advertiser/campaigns/new?campaignId=${campaignId}`,
      };
    else if (invoice) next = { label: "Pay invoice", href: `${base}/invoices/${invoice.id}` };
    else if (editable) next = { label: "Review and submit", href: `${base}?manage=review#manage` };
    else next = { label: "View campaign details", href: `${base}?details=quotation#quotation` };
  }
  return (
    <div className="animate-rise">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="text-green mb-2 text-sm font-semibold">{statusLabel[campaign.status]}</p>
          <h1 className="font-display max-w-2xl text-3xl font-semibold md:text-4xl">
            {campaign.name}
          </h1>
          <p className="text-muted mt-3 text-sm">
            {formatDateRange(campaign.start_at, campaign.end_at)}
          </p>
        </div>
      </div>
      <section
        aria-label="Next step"
        className="mb-7 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-[#f0f7ed] p-5"
      >
        <p className="max-w-xl text-sm leading-6 md:text-base">{sentences[campaign.status]}</p>
        <Link href={next.href} className="brand-action">
          {next.label} <span aria-hidden="true">→</span>
        </Link>
      </section>
      <div className="mb-6 grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <Panel className="overflow-hidden">
          <div className="border-edge flex items-center justify-between border-b px-5 py-4">
            <h2 className="font-semibold">Your advert</h2>
            {canWrite && !terminal ? (
              <Link
                href={`/advertiser/campaigns/new?campaignId=${campaign.id}`}
                className="text-green text-sm"
              >
                Edit artwork
              </Link>
            ) : null}
          </div>
          <div className="h-56 md:h-64">
            <CampaignArtwork name={campaign.name} fileId={previewFile(creativeItems)} />
          </div>
          {!artwork.available ? (
            <p className="text-muted px-5 pb-4 text-sm">
              Artwork couldn&apos;t be loaded.{" "}
              <Link href={base} className="underline">
                Try again
              </Link>
            </p>
          ) : !creativeItems.length ? (
            <p className="text-muted px-5 py-4 text-sm">
              Add your artwork to bring this campaign to life.
            </p>
          ) : null}
        </Panel>
        <Panel className="overflow-hidden">
          <h2 className="border-edge border-b px-5 py-4 font-semibold">Where your advert goes</h2>
          <div className="h-40 md:h-44">
            {areas.available ? (
              <AreaGraphic areas={areas.data.items} />
            ) : (
              <p className="text-muted p-5 text-sm">
                The campaign area couldn&apos;t be loaded.{" "}
                <Link href={base} className="underline">
                  Try again
                </Link>
              </p>
            )}
          </div>
          <p className="text-muted px-5 py-4 text-sm">
            {areas.available ? areas.data.items.map((area) => area.name).join(" · ") : ""}
          </p>
        </Panel>
      </div>
      <Panel className="mb-7 p-5 md:p-6">
        <BudgetUsed
          value={recordedBudget(
            campaign,
            commercial.available ? commercial.data.budget_evaluations : undefined,
          )}
        />
      </Panel>
      <div className="grid gap-4">
        <details
          id="details"
          className="brand-disclosure"
          open={Boolean(query.details || query.commercial_error)}
        >
          <summary>
            Details{" "}
            <span className="text-muted mr-5 ml-auto hidden text-sm font-normal md:inline">
              Quotation, dates and artwork
            </span>
          </summary>
          <div className="disclosure-body">
            <dl className="mb-6 grid gap-5 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">About this campaign</dt>
                <dd className="mt-1">{campaign.description || campaign.name}</dd>
              </div>
              <div>
                <dt className="text-muted">Total budget</dt>
                <dd className="mt-1 font-semibold">
                  {formatMoney(campaign.budget_amount, campaign.currency)}
                </dd>
              </div>
              {summary.available ? (
                <div>
                  <dt className="text-muted">Cars on the road</dt>
                  <dd className="mt-1">{formatCount(summary.data.assignments.active)}</dd>
                </div>
              ) : null}
            </dl>
            <div id="quotation" className="scroll-mt-24">
              {commercial.available ? (
                <CommercialPanel
                  campaignId={campaign.id}
                  canRequestQuotation={canWrite && !terminal}
                  commercial={commercial.data}
                  error={
                    query.commercial_error
                      ? "That request didn't go through. Please try again."
                      : undefined
                  }
                />
              ) : (
                <DataUnavailable
                  title="Quotation unavailable"
                  reason={commercial.reason}
                  retryHref={base}
                />
              )}
            </div>
            {artwork.available && creativeItems.length ? (
              <section className="mt-6">
                <h2 className="font-semibold">Artwork files</h2>
                <ul className="divide-edge divide-y">
                  {creativeItems.map((item) => (
                    <li
                      key={item.id}
                      className="flex flex-wrap items-center justify-between gap-3 py-4"
                    >
                      <div>
                        <p className="text-sm font-medium">{item.name}</p>
                        <p className="text-muted mt-1 text-xs">
                          {
                            (
                              {
                                draft: "Ready to submit",
                                pending_review: "Terrax Media is reviewing this artwork",
                                approved: "Approved",
                                rejected: "Changes needed",
                                archived: "Archived",
                                ready: "Upload this artwork again",
                              } as Record<string, string>
                            )[item.status]
                          }
                        </p>
                        {item.status === "rejected" ? (
                          <p className="text-coral mt-2 text-sm">
                            {artworkReasons.get(item.id) ??
                              "The feedback could not be loaded. Please try again."}
                          </p>
                        ) : null}
                      </div>
                      {canWrite && !terminal ? (
                        <CreativeStatusActions
                          campaignId={campaign.id}
                          creativeId={item.id}
                          status={item.status}
                        />
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {history.available ? (
              <section className="mt-6">
                <h2 className="font-semibold">Campaign updates</h2>
                <ul className="mt-3 grid gap-2 text-sm">
                  {history.data.items.map((event) => (
                    <li key={event.id}>
                      <span>
                        {statusLabel[event.new_status]} · {formatDate(event.created_at)}
                      </span>
                      {event.rejection_reason ? (
                        <p className="text-coral mt-1">{event.rejection_reason}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : (
              <DataUnavailable
                title="Campaign updates unavailable"
                reason={history.reason}
                retryHref={base}
                className="mt-6"
              />
            )}
          </div>
        </details>
        {canWrite && !terminal ? (
          <details id="manage" className="brand-disclosure" open={Boolean(query.manage)}>
            <summary>
              Manage{" "}
              <span className="text-muted mr-5 ml-auto hidden text-sm font-normal md:inline">
                Changes and cancellation
              </span>
            </summary>
            <div className="disclosure-body">
              {editable ? (
                <StatusActions campaignId={campaign.id} status={campaign.status} />
              ) : null}
              {changes.available ? (
                changeable || changes.data.items.length ? (
                  <CampaignChangePanel
                    campaignId={campaign.id}
                    clientRequestId={randomUUID()}
                    currency={campaign.currency}
                    requests={changes.data.items}
                    editable={changeable}
                  />
                ) : null
              ) : (
                <DataUnavailable
                  title="Campaign changes unavailable"
                  reason={changes.reason}
                  retryHref={base}
                />
              )}
              {["approved", "scheduled", "active", "paused"].includes(campaign.status) ? (
                <CampaignCancellationPanel campaignId={campaign.id} campaignName={campaign.name} />
              ) : null}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}
