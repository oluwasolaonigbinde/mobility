import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { LinkForm } from "./link-form";
import { TerminalPlanningActionForm } from "./operation-form";
import { SourceForm } from "./source-form";

export const metadata: Metadata = { title: "Planning sources" };

export default async function PlanningSourcesPage() {
  const api = createApiClient(await getSessionToken());
  const [{ data }, { data: linkData }, { data: campaignData }] = await Promise.all([
    api.GET("/api/v1/advertiser/retargeting-sources"),
    api.GET("/api/v1/advertiser/retargeting-source-links"),
    api.GET("/api/v1/advertiser/campaigns", {
      params: { query: { limit: 100, offset: 0 } },
    }),
  ]);
  const items = data?.items ?? [];
  const links = linkData?.items ?? [];
  const campaigns = campaignData?.items ?? [];
  const recommendations = new Map(
    await Promise.all(
      links.map(async (link) => {
        const { data: recommendation } = await api.GET(
          "/api/v1/advertiser/retargeting-source-links/{link_id}/recommendations",
          { params: { path: { link_id: link.id } } },
        );
        return [link.id, recommendation] as const;
      }),
    ),
  );
  const zoneGroups = await Promise.all(
    campaigns.map(async (campaign) => {
      const { data: zones } = await api.GET("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
        params: {
          path: { campaign_id: campaign.id },
          query: { limit: 100, offset: 0, zone_type: "target" },
        },
      });
      return (zones?.items ?? []).map((zone) => ({
        id: zone.id,
        campaignId: campaign.id,
        label: zone.name,
      }));
    }),
  );
  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader title="Planning sources" eyebrow="Aggregate-only retargeting inputs" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          {items.length === 0 ? (
            <EmptyState
              title="No planning sources"
              body="Record an allowlisted aggregate source to begin planning."
            />
          ) : (
            <Panel className="overflow-hidden">
              <div className="divide-edge divide-y">
                {items.map((source) => (
                  <article key={source.id} className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="font-medium">{source.source_type}</h2>
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
                        </div>
                        <p className="micro text-faint mt-2">
                          Expires {formatDate(source.expires_at)}
                        </p>
                        <p className="micro text-faint mt-1 font-mono">
                          Evidence {source.snapshot_sha256}
                        </p>
                      </div>
                      {source.status === "active" ? (
                        <TerminalPlanningActionForm
                          kind="deactivate-source"
                          resourceId={source.id}
                          label="Deactivate"
                        />
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </Panel>
          )}
          <section className="mt-5" aria-labelledby="source-links-heading">
            <h2 id="source-links-heading" className="mb-3 font-medium">
              Campaign and target-zone links
            </h2>
            {links.length === 0 ? (
              <EmptyState
                title="No source links"
                body="Link an active source to an owned campaign target zone and bounded time window."
              />
            ) : (
              <Panel className="divide-edge divide-y overflow-hidden">
                {links.map((link) => {
                  const recommendation = recommendations.get(link.id);
                  return (
                    <article key={link.id} className="p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <StatusChip tone={link.status === "active" ? "green" : "default"}>
                              {link.status}
                            </StatusChip>
                            {link.stale ? (
                              <StatusChip tone="coral">stale parent state</StatusChip>
                            ) : null}
                          </div>
                          <p className="micro text-faint mt-2 font-mono">
                            Campaign {link.campaign_id}
                          </p>
                          <p className="micro text-faint mt-1 font-mono">
                            Target zone {link.zone_id}
                          </p>
                          <p className="micro text-faint mt-1">
                            {formatDate(link.start_at)} → {formatDate(link.end_at)}
                          </p>
                        </div>
                        {link.status === "active" ? (
                          <TerminalPlanningActionForm
                            kind="remove-link"
                            resourceId={link.id}
                            label="Remove link"
                          />
                        ) : null}
                      </div>
                      <div className="border-edge mt-4 border-t pt-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium">
                              Follow-up targeting recommendations
                            </p>
                            <p className="micro text-faint mt-1">
                              {recommendation?.state === "ready"
                                ? `${recommendation.recommendations.length} aggregate geography/time recommendation${recommendation.recommendations.length === 1 ? "" : "s"}`
                                : recommendation?.state === "suppressed"
                                  ? "All cells are suppressed by the current disclosure floor."
                                  : recommendation?.state === "stale"
                                    ? "The issued aggregate is stale and cannot be exported."
                                    : "No issued aggregate is available yet."}
                            </p>
                          </div>
                          {recommendation?.state === "ready" &&
                          recommendation.segment_id &&
                          recommendation.export_approval_id ? (
                            <form
                              action={`/api/advertiser/exposure-segments/${recommendation.segment_id}/export`}
                              method="post"
                            >
                              <input
                                type="hidden"
                                name="approval_id"
                                value={recommendation.export_approval_id}
                              />
                              <button className="border-edge hover:border-coral rounded-lg border px-3 py-2 text-sm">
                                Download controlled CSV
                              </button>
                            </form>
                          ) : null}
                          {recommendation?.state === "ready" &&
                          !recommendation.export_approval_id ? (
                            <p className="micro text-faint">
                              Awaiting current privacy approval for controlled export.
                            </p>
                          ) : null}
                        </div>
                        {recommendation?.state === "ready"
                          ? recommendation.recommendations.slice(0, 3).map((item) => (
                              <p
                                key={`${item.coverage_cell}-${item.window_start_at}`}
                                className="micro mt-2"
                              >
                                #{item.rank} {item.coverage_cell} ·{" "}
                                {formatDate(item.window_start_at)} →{" "}
                                {formatDate(item.window_end_at)}
                              </p>
                            ))
                          : null}
                        {recommendation?.state === "ready" && recommendation.uncertainty ? (
                          <p className="micro text-faint mt-3">{recommendation.uncertainty}</p>
                        ) : null}
                        <p className="micro text-faint mt-1">{recommendation?.disclaimer}</p>
                        {recommendation?.state === "ready" && recommendation.provenance ? (
                          <p className="micro text-faint mt-2 font-mono">
                            Segment v{recommendation.provenance.segment_version} · Evidence{" "}
                            {recommendation.provenance.segment_snapshot_sha256}
                          </p>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </Panel>
            )}
          </section>
        </div>
        <div className="grid h-fit gap-5">
          <Panel className="p-5">
            <h2 className="mb-4 font-medium">Record aggregate source</h2>
            <SourceForm />
          </Panel>
          <Panel className="p-5">
            <h2 className="mb-4 font-medium">Link source to campaign</h2>
            <LinkForm
              sources={items
                .filter((source) => source.status === "active")
                .map((source) => ({ id: source.id, label: source.source_type }))}
              campaigns={campaigns.map((campaign) => ({ id: campaign.id, label: campaign.name }))}
              zones={zoneGroups.flat()}
            />
          </Panel>
        </div>
      </div>
    </div>
  );
}
