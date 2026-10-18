import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { requireRole, isAdvertiserViewer } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { loadCampaignAreas } from "@/lib/advertiser/campaign-visuals";
import { getSessionToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";
import { DataUnavailable } from "@/components/ui/data-unavailable";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { labelFor, linkStatusLabel, sourceDisplayLabel, sourceStatusLabel } from "./labels";
import { LinkForm } from "./link-form";
import { TerminalPlanningActionForm } from "./operation-form";
import { SourceForm } from "./source-form";

export const metadata: Metadata = { title: "Reach these people again" };

const suggestionState: Record<string, string> = {
  suppressed:
    "Not enough campaign activity here yet to show suggestions without identifying anyone.",
  stale: "These suggestions are out of date, so they can't be downloaded.",
};

export default async function PlanningSourcesPage({
  params,
}: {
  params: Promise<{ campaignId: string }>;
}) {
  const { campaignId } = await params;
  const me = await requireRole("advertiser");
  const canWrite = !isAdvertiserViewer(me);
  const RETRY_HREF = `/advertiser/campaigns/${campaignId}/retargeting`;
  const api = createApiClient(await getSessionToken());
  const [sourcesResult, linksResult, campaignResult] = await Promise.all([
    loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/retargeting-sources")),
    loadAdvertiserPageData(() => api.GET("/api/v1/advertiser/retargeting-source-links")),
    loadAdvertiserPageData(() =>
      api.GET("/api/v1/advertiser/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      }),
    ),
  ]);

  const header = (
    <PageHeader
      title="Reach these people again"
      eyebrow="Plan your online follow-up around this campaign’s areas and times."
    />
  );

  if (!campaignResult.available && campaignResult.reason === "missing") notFound();
  if (campaignResult.available && campaignResult.data.id !== campaignId) notFound();
  const unavailable = [sourcesResult, linksResult, campaignResult].find(
    (result) => !result.available,
  );
  if (unavailable && !unavailable.available) {
    return (
      <div className="animate-rise mx-auto max-w-6xl min-w-0">
        {header}
        <DataUnavailable
          title="Couldn't load your audiences — try again"
          reason={unavailable.reason}
          retryHref={RETRY_HREF}
        />
      </div>
    );
  }
  const items = sourcesResult.available ? sourcesResult.data.items : [];
  const links = linksResult.available
    ? linksResult.data.items.filter((link) => link.campaign_id === campaignId)
    : [];
  const campaigns = campaignResult.available ? [campaignResult.data] : [];

  const recommendations = new Map(
    await Promise.all(
      links.map(async (link) => {
        const recommendation = await loadAdvertiserPageData(() =>
          api.GET("/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations", {
            params: { path: { link_id: link.id } },
          }),
        );
        return [link.id, recommendation] as const;
      }),
    ),
  );
  const zoneResults = await Promise.all(
    campaigns.map(async (campaign) => {
      const zones = await loadCampaignAreas(api, campaign.id);
      return zones.available
        ? zones.data.items.map((zone) => ({
            id: zone.id,
            campaignId: campaign.id,
            label: zone.name,
          }))
        : null;
    }),
  );
  const zonesIncomplete = zoneResults.some((zones) => zones === null);
  const zoneOptions = zoneResults.flatMap((zones) => zones ?? []);
  const campaignNames = new Map(campaigns.map((campaign) => [campaign.id, campaign.name]));
  const zoneNames = new Map(zoneOptions.map((zone) => [zone.id, zone.label]));
  const sourceNames = new Map(items.map((source) => [source.id, sourceDisplayLabel(source)]));
  return (
    <div className="animate-rise mx-auto max-w-6xl min-w-0">
      {header}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <h2 className="mb-3 font-medium">Your audiences</h2>
          {items.length === 0 ? (
            <EmptyState
              title="No audiences yet"
              body="Describe an audience you already have to start getting suggestions."
            />
          ) : (
            <Panel className="overflow-hidden">
              <div className="divide-edge divide-y">
                {items.map((source) => (
                  <article key={source.id} className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium">{sourceDisplayLabel(source)}</h3>
                          <StatusChip
                            tone={
                              source.status === "active"
                                ? "green"
                                : source.status === "expired"
                                  ? "amber"
                                  : "default"
                            }
                          >
                            {labelFor(sourceStatusLabel, source.status)}
                          </StatusChip>
                        </div>
                        <p className="text-faint mt-2 text-sm">
                          {source.status === "active" ? "Used until" : "Ended"}{" "}
                          {formatDateTime(source.deactivated_at ?? source.expires_at)} · Nigeria
                          time (WAT)
                        </p>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </Panel>
          )}
          <section className="mt-5" aria-labelledby="source-links-heading">
            <h2 id="source-links-heading" className="font-medium">
              Audiences linked to campaign areas
            </h2>
            <p className="text-muted mt-1 mb-3 text-sm">
              Each link pairs one audience with one area of a campaign for a date range. Suggested
              areas and times for that pair show here.
            </p>
            {links.length === 0 ? (
              <EmptyState
                title="Nothing linked yet"
                body="Link an audience to a campaign area to see suggestions for that area."
              />
            ) : (
              <Panel className="divide-edge divide-y overflow-hidden">
                {links.map((link) => {
                  const loaded = recommendations.get(link.id);
                  const recommendation = loaded?.available ? loaded.data : undefined;
                  const ready =
                    recommendation?.state === "ready" && recommendation.campaign_id === campaignId;
                  return (
                    <article key={link.id} className="p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <StatusChip tone={link.status === "active" ? "green" : "default"}>
                              {labelFor(linkStatusLabel, link.status)}
                            </StatusChip>
                            {link.stale ? (
                              <StatusChip tone="coral">Changed since linked</StatusChip>
                            ) : null}
                          </div>
                          <p className="mt-2 text-sm">
                            Audience: {sourceNames.get(link.source_id) ?? "name unavailable"}
                          </p>
                          <p className="mt-2 text-sm">
                            Campaign: {campaignNames.get(link.campaign_id) ?? "name unavailable"}
                          </p>
                          <p className="text-muted mt-1 text-sm">
                            Area: {zoneNames.get(link.zone_id) ?? "name unavailable"}
                          </p>
                          <p className="text-faint mt-1 text-sm">
                            {formatDateTime(link.start_at)} → {formatDateTime(link.end_at)} ·
                            Nigeria time (WAT)
                          </p>
                        </div>
                        {canWrite && link.status === "active" ? (
                          <div className="max-w-56 text-right">
                            <TerminalPlanningActionForm
                              campaignId={campaignId}
                              resourceId={link.id}
                              label="Unlink"
                            />
                            <p className="text-faint mt-2 text-sm">
                              Stops suggestions for this pair. The campaign and audience stay as
                              they are; you can link them again while both are in use.
                            </p>
                          </div>
                        ) : null}
                      </div>
                      <div className="border-edge mt-4 border-t pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium">Suggested areas and times</p>
                            <p className="text-faint mt-1 text-sm">
                              {!loaded?.available
                                ? "Suggestions couldn't be loaded right now."
                                : ready
                                  ? `${recommendation.recommendations.length} suggestion${recommendation.recommendations.length === 1 ? "" : "s"}`
                                  : (suggestionState[recommendation?.state ?? ""] ??
                                    "No suggestions for this area yet.")}
                            </p>
                          </div>
                          {ready && recommendation.segment_id ? (
                            <form
                              action={`/api/advertiser/exposure-segments/${recommendation.segment_id}/export`}
                              method="post"
                            >
                              <button className="border-edge hover:border-coral rounded-lg border px-3 py-2 text-sm">
                                Download suggestions (CSV)
                              </button>
                            </form>
                          ) : null}
                        </div>
                        {ready
                          ? recommendation.recommendations.slice(0, 3).map((item) => (
                              <div
                                key={`${item.coverage_cell}-${item.window_start_at}`}
                                className="mt-2 text-sm"
                              >
                                <p>
                                  Suggestion {item.rank} ·{" "}
                                  {zoneNames.get(link.zone_id) ?? "Area name unavailable"}
                                </p>
                                <p>
                                  {formatDateTime(item.window_start_at)} →{" "}
                                  {formatDateTime(item.window_end_at)} · Nigeria time (WAT)
                                </p>
                                <p className="text-muted mt-1">{item.rationale}</p>
                              </div>
                            ))
                          : null}
                        {ready ? (
                          <div className="text-faint mt-3 space-y-2 text-sm">
                            <p>
                              Based on where cars travelled for this campaign, matched to this
                              audience and area.
                            </p>
                            {recommendation.uncertainty ? (
                              <p>{recommendation.uncertainty}</p>
                            ) : null}
                            <p>{recommendation.disclaimer}</p>
                          </div>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </Panel>
            )}
          </section>
        </div>
        {canWrite ? (
          <div className="grid h-fit min-w-0 gap-5">
            <Panel className="p-5">
              <h2 className="mb-4 font-medium">Describe an audience</h2>
              <SourceForm campaignId={campaignId} />
            </Panel>
            <Panel className="p-5">
              <h2 className="font-medium">Link an audience to a campaign area</h2>
              <p className="text-muted mt-1 mb-4 text-sm">
                Linking doesn&apos;t change the campaign or send ads. It lets Cardvert suggest areas
                and times from that campaign&apos;s routes for your own online follow-up.
              </p>
              <LinkForm
                scopeCampaignId={campaignId}
                sources={items
                  .filter((source) => source.status === "active")
                  .map((source) => ({
                    id: source.id,
                    label: sourceDisplayLabel(source),
                  }))}
                campaigns={campaigns.map((campaign) => ({ id: campaign.id, label: campaign.name }))}
                zones={zoneOptions}
                zonesIncomplete={zonesIncomplete}
              />
            </Panel>
          </div>
        ) : null}
      </div>
    </div>
  );
}
