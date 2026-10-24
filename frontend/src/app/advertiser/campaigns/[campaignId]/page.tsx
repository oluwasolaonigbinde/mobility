import type { Metadata } from "next";
import { randomUUID } from "node:crypto";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { requireRole } from "@/lib/auth/current-user";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDateRange, formatMoney } from "@/lib/format";
import { statusLabel } from "@/lib/campaigns/status";
import { Panel } from "@/components/ui/panel";
import { CampaignMap } from "@/components/campaigns/campaign-map";
import { PerformanceCard } from "@/components/campaigns/performance-card";
import { IconTile } from "@/components/brand/portal-icon";
import { BudgetUsed } from "@/components/campaigns/budget-used";
import { loadCampaignVisuals } from "@/lib/advertiser/campaign-visuals";
import { loadLivePositions } from "@/lib/advertiser/engagement";
import { loadPerformance } from "@/lib/advertiser/performance";
import { campaignDay } from "@/lib/campaigns/day-progress";
import { bookedBudget } from "@/lib/advertiser/budget-display";
import { isOutstandingInvoice } from "@/lib/billing/commercial-history";
import { readCampaignCancellationRequests } from "@/lib/api/audit-batch2";
import { isCancellableCampaign } from "@/lib/campaigns/cancellation";
import { StatusActions } from "./status-actions";
import { CommercialPanel } from "./commercial-panel";
import { CampaignAssets } from "./campaign-assets";
import { CampaignChangePanel } from "./campaign-change-panel";
import { CampaignCancellationPanel } from "./campaign-cancellation-panel";

export const metadata: Metadata = { title: "Campaign" };
const sentences: Record<string, string> = {
  draft: "Finish setting up your campaign.",
  pending_review: "Terrax Media is reviewing your campaign.",
  rejected: "Terrax Media has asked for a few changes.",
  approved: "Your campaign is approved. Terrax Media is arranging the next steps.",
  active: "Your campaign is running.",
  paused: "Your campaign is paused. Contact Terrax Media about the next steps.",
  finished: "Your campaign has finished.",
  cancelled: "This campaign has been cancelled.",
};
const pauseSentences = {
  budget: "Your campaign is paused for a budget check. Contact Terrax Media about the next steps.",
  operational:
    "Terrax Media has paused your campaign while it checks an operational issue. Contact Terrax Media about the next steps.",
  unknown: "Your campaign is paused. Contact Terrax Media about the next steps.",
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
  await requireRole("advertiser");
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
  const cancellable = isCancellableCampaign(campaign.status);
  const [visuals, commercial, history, changes, cancellations, live, performance] =
    await Promise.all([
      loadCampaignVisuals(api, campaignId),
      loadAdvertiserPageData(() =>
        api.GET("/api/v1/advertiser/campaigns/{campaign_id}/commercial", {
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
      cancellable
        ? loadAdvertiserPageData(() => readCampaignCancellationRequests(api, campaignId))
        : null,
      loadLivePositions(api, campaignId),
      loadPerformance(api, campaignId),
    ]);
  // A request already sent shows its status instead of a second form (REQ-194).
  const cancellation =
    !cancellable || !cancellations ? null : !cancellations.available ? (
      <DataUnavailable
        title="Cancellation request unavailable"
        reason={cancellations.reason}
        retryHref={base}
        className="mt-6"
      />
    ) : (
      <CampaignCancellationPanel
        campaignId={campaign.id}
        campaignName={campaign.name}
        pendingThreadId={
          cancellations.data.items.find(
            (item) =>
              item.category === "campaign_cancellation" &&
              (item.status === "open" || item.status === "answered"),
          )?.id
        }
      />
    );
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
            result.available ? (result.data.items[0]?.rejection_reason ?? undefined) : undefined,
          ] as const;
        }),
    ),
  );
  const terminal = ["finished", "cancelled"].includes(campaign.status);
  const artworkAuthorityAvailable =
    campaign.status === "active" || (commercial.available && "production_start" in commercial.data);
  const artworkLocked =
    campaign.status === "active" ||
    (commercial.available && Boolean(commercial.data.production_start?.started_at));
  const positions =
    live.available && live.data.campaign_id === campaignId ? live.data.positions : null;
  const assets = await CampaignAssets({
    api,
    campaignId,
    campaignName: campaign.name,
    items: creativeItems,
    canWrite: !terminal,
    locked: artworkLocked,
    changeAvailable: artworkAuthorityAvailable,
    available: artwork.available,
    reasons: artworkReasons,
  });
  const editable = ["draft", "rejected"].includes(campaign.status);
  const changeable = ["approved", "active", "paused"].includes(campaign.status);
  const invoice = commercial.available
    ? commercial.data.invoices?.find(isOutstandingInvoice)
    : undefined;
  let next = { label: "See results", href: `${base}/report` };
  if (campaign.status === "cancelled")
    next = { label: "View invoices", href: `/advertiser/billing#campaign-${campaignId}` };
  else if (campaign.status === "paused")
    next = { label: "Contact Terrax Media", href: "/advertiser/help" };
  else if (!terminal && campaign.status !== "active") {
    if (editable && (!campaign.start_at || !campaign.end_at || !campaign.budget_amount))
      next = { label: "Add campaign details", href: `${base}/edit` };
    else if (editable && areas.available && areas.data.total === 0)
      next = { label: "Choose your area", href: `${base}/zones` };
    else if (!commercial.available || !artwork.available || (editable && !areas.available))
      next = { label: "Try again", href: base };
    else if (!creativeItems.length)
      next = {
        label: "Add your artwork",
        href: `/advertiser/campaigns/new?campaignId=${campaignId}`,
      };
    else if (!commercial.data.terms && commercial.data.revisions?.length)
      next = {
        label: "Review your quotation",
        href: `${base}?details=quotation#quotation`,
      };
    else if (!commercial.data.terms)
      next = {
        label: commercial.data.quote_request ? "View campaign details" : "Request a quotation",
        href: `${base}?details=quotation#quotation`,
      };
    else if (creativeItems.some((item) => ["draft", "rejected"].includes(item.status)))
      next = {
        label: "Add or update artwork",
        href: `/advertiser/campaigns/new?campaignId=${campaignId}`,
      };
    else if (invoice)
      next = {
        label: "Pay invoice",
        href: `/advertiser/billing/${campaignId}/invoices/${invoice.id}`,
      };
    else if (editable) next = { label: "Review and submit", href: `${base}?manage=review#manage` };
    else next = { label: "View campaign details", href: `${base}?details=quotation#quotation` };
  }
  if (artworkLocked && next.href.startsWith("/advertiser/campaigns/new"))
    next = { label: "Ask Terrax to change it", href: `${base}#artwork-change` };
  return (
    <div className="animate-rise">
      <section className="portal-hero mb-6" aria-label="Next step">
        <div className="portal-hero-copy">
          <p className="mb-3 text-sm font-semibold text-[#c8f6d0]">
            {statusLabel[campaign.status]}
          </p>
          <h1 className="font-display max-w-2xl text-3xl font-semibold md:text-4xl">
            {campaign.name}
          </h1>
          <p className="mt-3 text-base text-[#e4f0df]">
            {formatDateRange(campaign.start_at, campaign.end_at)}
          </p>
          <p className="mt-2 text-sm font-semibold text-[#f2c94c]">
            {campaignDay(campaign.start_at, campaign.end_at)}
          </p>
          <p className="mt-4 text-sm text-[#e4f0df]">
            {campaign.status === "paused"
              ? pauseSentences[campaign.pause_kind ?? "unknown"]
              : sentences[campaign.status]}
          </p>
          <Link href={next.href} className="brand-action mt-5">
            {next.label} <span aria-hidden="true">→</span>
          </Link>
        </div>
        <div className="portal-hero-art" aria-hidden="true" />
      </section>
      <div className="mb-6 grid gap-5 lg:grid-cols-2">
        <Panel className="overflow-hidden">
          <div className="border-edge flex items-center justify-between gap-3 border-b px-5 py-4">
            <h2 className="font-semibold">On the road now</h2>
            <a href={base} className="text-green text-sm font-semibold">
              Refresh
            </a>
          </div>
          <div className="h-64">
            {areas.available ? (
              <CampaignMap
                areas={areas.data.items.map(({ id, name, geometry, zone_type }) => ({
                  id,
                  name,
                  geometry,
                  zone_type,
                }))}
                positions={positions ?? []}
              />
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
            {positions === null
              ? "Driving positions couldn't be loaded. Refresh to try again."
              : positions.length === 0
                ? "No cars driving right now"
                : `${positions.length} ${positions.length === 1 ? "car" : "cars"} driving · as of about 15 minutes ago`}
          </p>
          <p className="text-muted px-5 pb-4 text-sm">
            {areas.available ? areas.data.items.map((area) => area.name).join(" · ") : ""}{" "}
            <Link href={`${base}/map`} className="text-green font-semibold">
              View coverage history
            </Link>
          </p>
        </Panel>
        <Panel>
          <PerformanceCard {...performance} cars={positions?.length ?? null} />
        </Panel>
      </div>
      {assets}
      <Panel className="mb-7 flex items-start gap-4 p-5 md:p-6">
        <IconTile name="wallet" tone="gold" />
        <div className="min-w-0 flex-1">
          <BudgetUsed value={bookedBudget(campaign)} />
        </div>
      </Panel>
      <p className="mb-6 text-sm">
        <Link
          href={`/advertiser/billing#campaign-${campaignId}`}
          className="text-green font-semibold"
        >
          View invoices in Billing →
        </Link>
      </p>
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
            </dl>
            <div id="quotation" className="scroll-mt-24">
              {commercial.available ? (
                <CommercialPanel
                  campaignId={campaign.id}
                  canRequestQuotation={!terminal}
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
        {!terminal ? (
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
              {cancellation}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}
