import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { QueueUnavailable } from "../../queue-search";
import { adminStatus } from "@/lib/status/admin";
import Link from "next/link";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { HighExposureZoneInsights } from "@/components/analytics/high-exposure-zone-insights";

export const metadata: Metadata = { title: "Audiences" };

async function readDetails<T, R>(items: T[], read: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = [];
  for (let offset = 0; offset < items.length; offset += 4)
    results.push(...(await Promise.all(items.slice(offset, offset + 4).map(read))));
  return results;
}

export default async function AdminPlanningSourcesPage() {
  const api = createApiClient(await getSessionToken());
  const [sourcesResult, linksResult] = await Promise.all([
    loadAdvertiserPageData(() => api.GET("/api/v1/admin/retargeting-sources")),
    loadAdvertiserPageData(() => api.GET("/api/v1/admin/retargeting-source-links")),
  ]);
  if (!sourcesResult.available || !linksResult.available) return <QueueUnavailable />;
  const data = sourcesResult.data;
  const items = data.items;
  const links = linksResult.data.items;
  const campaignIds = [...new Set(links.map((link) => link.campaign_id))];
  const companyNames = new Map<string, string>(),
    campaignNames = new Map<string, string>();
  const companyIds = [
    ...new Set([
      ...items.map((row) => row.organization_id),
      ...links.map((row) => row.organization_id),
    ]),
  ];
  const reads = [
    ...companyIds.map((id) => ({ kind: "company" as const, id })),
    ...campaignIds.map((id) => ({ kind: "campaign" as const, id })),
  ];
  for (let index = 0; index < reads.length; index += 4) {
    await Promise.all(
      reads.slice(index, index + 4).map(async ({ kind, id }) => {
        if (kind === "company") {
          const { data } = await api
            .GET("/api/v1/admin/advertiser-organizations/{organization_id}/company", {
              params: { path: { organization_id: id } },
            })
            .catch(() => ({ data: undefined }));
          if (data?.id === id) companyNames.set(id, data.name);
        } else {
          const { data } = await api
            .GET("/api/v1/admin/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })
            .catch(() => ({ data: undefined }));
          if (data?.id === id) campaignNames.set(id, data.name);
        }
      }),
    );
  }
  const namesFailed =
    companyNames.size !== companyIds.length || campaignNames.size !== campaignIds.length;
  if (namesFailed) return <QueueUnavailable />;
  const zoneInsights = new Map(
    await readDetails(campaignIds, async (campaignId) => {
      const insight = await loadAdvertiserPageData(() =>
        api.GET("/api/v1/admin/campaigns/{campaign_id}/zone-insights", {
          params: { path: { campaign_id: campaignId } },
        }),
      );
      return [campaignId, insight.available ? insight.data : undefined] as const;
    }),
  );
  const recommendations = new Map(
    await readDetails(links, async (link) => {
      const recommendation = await loadAdvertiserPageData(() =>
        api.GET("/api/v1/admin/retargeting-source-links/{link_id}/recommendations", {
          params: { path: { link_id: link.id } },
        }),
      );
      return [link.id, recommendation.available ? recommendation.data : undefined] as const;
    }),
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Audiences"
        eyebrow={`${data.total} advertiser audience source${data.total === 1 ? "" : "s"}`}
      />
      {items.length === 0 ? (
        <EmptyState title="No audiences" body="Advertiser aggregate audiences will appear here." />
      ) : (
        <Panel className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-edge text-muted border-b text-left">
                  <th className="px-5 py-3 font-normal">Type</th>
                  <th className="px-5 py-3 font-normal">Organization</th>
                  <th className="px-5 py-3 font-normal">Status</th>
                  <th className="px-5 py-3 font-normal">Expiry</th>
                  <th className="px-5 py-3 font-normal">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {items.map((source) => (
                  <tr key={source.id} className="border-edge/60 border-b last:border-0">
                    <td className="px-5 py-4">
                      {source.source_type === "manual_insight" ||
                      source.source_type === "manual-insight"
                        ? "Recorded audience"
                        : "Audience"}
                    </td>
                    <td className="px-5 py-4 font-mono text-xs">
                      <Link
                        className="underline"
                        href={`/admin/advertisers/${source.organization_id}`}
                      >
                        {companyNames.get(source.organization_id)}
                      </Link>
                    </td>
                    <td className="px-5 py-4">
                      <StatusChip
                        tone={
                          source.status === "active"
                            ? "green"
                            : source.status === "expired"
                              ? "amber"
                              : "default"
                        }
                      >
                        {adminStatus(source.status)}
                      </StatusChip>
                    </td>
                    <td className="px-5 py-4">{formatDate(source.expires_at)}</td>
                    <td className="px-5 py-4 font-mono text-xs">
                      <details>
                        <summary>Recorded source details</summary>
                        {source.snapshot_sha256}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <section className="mt-6" aria-labelledby="admin-source-links-heading">
        <h2 id="admin-source-links-heading" className="mb-3 font-medium">
          Campaign audiences
        </h2>
        {links.length === 0 ? (
          <EmptyState title="No campaign audiences" body="Campaign audiences will appear here." />
        ) : [...recommendations.values()].some((value) => !value) ? (
          <QueueUnavailable />
        ) : (
          <Panel className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-edge text-muted border-b text-left">
                    <th className="px-5 py-3 font-normal">Organization</th>
                    <th className="px-5 py-3 font-normal">Campaign</th>
                    <th className="px-5 py-3 font-normal">Target zone</th>
                    <th className="px-5 py-3 font-normal">Status</th>
                    <th className="px-5 py-3 font-normal">Window</th>
                    <th className="px-5 py-3 font-normal">Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((link) => {
                    const recommendation = recommendations.get(link.id);
                    return (
                      <tr key={link.id} className="border-edge/60 border-b last:border-0">
                        <td className="px-5 py-4 font-mono text-xs">
                          <Link
                            className="underline"
                            href={`/admin/advertisers/${link.organization_id}`}
                          >
                            {companyNames.get(link.organization_id)}
                          </Link>
                        </td>
                        <td className="px-5 py-4 font-mono text-xs">
                          <Link className="underline" href={`/admin/campaigns/${link.campaign_id}`}>
                            {campaignNames.get(link.campaign_id)}
                          </Link>
                        </td>
                        <td className="px-5 py-4 font-mono text-xs">
                          <details>
                            <summary>Area reference</summary>
                            {link.zone_id}
                          </details>
                        </td>
                        <td className="px-5 py-4">
                          <StatusChip tone={link.status === "active" ? "green" : "default"}>
                            {adminStatus(link.status)}
                          </StatusChip>
                          {link.stale ? (
                            <StatusChip tone="coral" className="ml-2">
                              Needs refresh
                            </StatusChip>
                          ) : null}
                        </td>
                        <td className="px-5 py-4 text-xs">
                          {formatDate(link.start_at)} → {formatDate(link.end_at)}
                        </td>
                        <td className="px-5 py-4 text-xs">
                          <StatusChip
                            tone={
                              recommendation?.state === "ready"
                                ? "green"
                                : recommendation?.state === "suppressed"
                                  ? "amber"
                                  : recommendation?.state === "stale"
                                    ? "coral"
                                    : "default"
                            }
                          >
                            {adminStatus(recommendation?.state ?? "empty", "audience")}
                          </StatusChip>
                          {recommendation?.state === "ready" &&
                          recommendation.recommendations[0] ? (
                            <p className="mt-2 font-mono">
                              {recommendation.recommendations[0].coverage_cell}
                            </p>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </section>
      {campaignIds.length > 0 ? (
        <section className="mt-6" aria-labelledby="admin-zone-insights-heading">
          <h2 id="admin-zone-insights-heading" className="mb-3 font-medium">
            Campaign area results
          </h2>
          {[...zoneInsights.values()].some((value) => !value) ? <QueueUnavailable /> : null}
          <div className="grid gap-4 lg:grid-cols-2">
            {campaignIds.map((campaignId) => {
              const insight = zoneInsights.get(campaignId);
              return insight ? (
                <div key={campaignId}>
                  <p className="micro text-faint mb-2 font-mono">
                    <Link className="underline" href={`/admin/campaigns/${campaignId}#results`}>
                      {campaignNames.get(campaignId)} results
                    </Link>
                  </p>
                  <HighExposureZoneInsights insight={insight} surface="admin" />
                </div>
              ) : null;
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
