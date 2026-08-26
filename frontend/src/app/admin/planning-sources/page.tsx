import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

export const metadata: Metadata = { title: "Planning source monitoring" };

export default async function AdminPlanningSourcesPage() {
  const api = createApiClient(await getSessionToken());
  const [{ data }, { data: linkData }] = await Promise.all([
    api.GET("/api/v1/admin/retargeting-sources"),
    api.GET("/api/v1/admin/retargeting-source-links"),
  ]);
  const items = data?.items ?? [];
  const links = linkData?.items ?? [];
  const recommendations = new Map(
    await Promise.all(
      links.map(async (link) => {
        const { data: recommendation } = await api.GET(
          "/api/v1/admin/retargeting-source-links/{link_id}/recommendations",
          { params: { path: { link_id: link.id } } },
        );
        return [link.id, recommendation] as const;
      }),
    ),
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Planning source monitoring"
        eyebrow={`${data?.total ?? 0} aggregate source${data?.total === 1 ? "" : "s"}`}
      />
      {items.length === 0 ? (
        <EmptyState
          title="No planning sources"
          body="Advertiser aggregate planning sources will appear here."
        />
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
                    <td className="px-5 py-4">{source.source_type}</td>
                    <td className="px-5 py-4 font-mono text-xs">{source.organization_id}</td>
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
                        {source.status}
                      </StatusChip>
                    </td>
                    <td className="px-5 py-4">{formatDate(source.expires_at)}</td>
                    <td className="px-5 py-4 font-mono text-xs">{source.snapshot_sha256}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <section className="mt-6" aria-labelledby="admin-source-links-heading">
        <h2 id="admin-source-links-heading" className="mb-3 font-medium">
          Campaign and target-zone links
        </h2>
        {links.length === 0 ? (
          <EmptyState title="No source links" body="Advertiser source linkages will appear here." />
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
                        <td className="px-5 py-4 font-mono text-xs">{link.organization_id}</td>
                        <td className="px-5 py-4 font-mono text-xs">{link.campaign_id}</td>
                        <td className="px-5 py-4 font-mono text-xs">{link.zone_id}</td>
                        <td className="px-5 py-4">
                          <StatusChip tone={link.status === "active" ? "green" : "default"}>
                            {link.status}
                          </StatusChip>
                          {link.stale ? (
                            <StatusChip tone="coral" className="ml-2">
                              stale
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
                            {recommendation?.state ?? "empty"}
                          </StatusChip>
                          {recommendation?.recommendations[0] ? (
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
      <p className="micro text-faint mt-5">
        Monitoring is read-only. Live use remains unavailable until legal/privacy approval evidence
        is recorded. Ad-platform activation remains disabled while EXT-AD-PLATFORM is missing.
      </p>
    </div>
  );
}
