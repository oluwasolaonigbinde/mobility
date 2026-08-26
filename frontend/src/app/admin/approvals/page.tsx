import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { formatDate, formatDateRange, formatMoney } from "@/lib/format";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { ReviewActions } from "./review-actions";
import { CreativeReviewActions } from "./creative-review-actions";
import { InstallationReviewActions } from "./installation-review-actions";

export const metadata: Metadata = { title: "Approvals" };

const PAGE_SIZE = 25;

export default async function AdminApprovalsPage() {
  const api = createApiClient(await getSessionToken());
  const { data: queue } = await api.GET("/api/v1/admin/campaigns/pending-review", {
    params: { query: { limit: PAGE_SIZE, offset: 0 } },
  });
  const { data: creativeQueue } = await api.GET("/api/v1/admin/creatives/pending-review", {
    params: { query: { limit: PAGE_SIZE, offset: 0 } },
  });
  const { data: installationQueue } = await api.GET("/api/v1/admin/installation-evidence/pending");
  const items = queue?.items ?? [];
  const histories = await Promise.all(
    items.map(async (campaign) => {
      const { data } = await api.GET("/api/v1/admin/campaigns/{campaign_id}/review-history", {
        params: { path: { campaign_id: campaign.id }, query: { limit: 10, offset: 0 } },
      });
      return [campaign.id, data?.items ?? []] as const;
    }),
  );
  const historyByCampaignId = new Map(histories);
  const creativeItems = creativeQueue?.items ?? [];
  const creativeHistories = await Promise.all(
    creativeItems.map(async ({ creative }) => {
      const { data } = await api.GET("/api/v1/admin/creatives/{creative_id}/review-history", {
        params: { path: { creative_id: creative.id }, query: { limit: 10, offset: 0 } },
      });
      return [creative.id, data?.items ?? []] as const;
    }),
  );
  const historyByCreativeId = new Map(creativeHistories);
  const installationItems = installationQueue?.items ?? [];
  const totalPending = (queue?.total ?? 0) + (creativeQueue?.total ?? 0) + installationItems.length;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Approvals"
        eyebrow={`${totalPending} item${totalPending === 1 ? "" : "s"} awaiting review`}
      />

      {items.length === 0 && creativeItems.length === 0 && installationItems.length === 0 ? (
        <EmptyState
          title="Nothing awaiting review"
          body="New submissions will appear here with their immutable review history."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {items.length ? <h2 className="text-lg font-medium">Campaigns</h2> : null}
          {items.map((campaign) => {
            const history = historyByCampaignId.get(campaign.id) ?? [];
            const submission = history.find((event) => event.new_status === "pending_review");
            return (
              <Panel
                key={campaign.id}
                className="p-5"
                data-testid={`campaign-approval-${campaign.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusChip tone={statusTone[campaign.status]}>
                        {statusLabel[campaign.status]}
                      </StatusChip>
                      <h2 className="font-medium">{campaign.name}</h2>
                    </div>
                    <p className="text-muted mt-2 text-sm">
                      {campaign.description ?? "No description provided."}
                    </p>
                    <dl className="micro text-faint mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">
                      <div>
                        <dt className="inline">Advertiser: </dt>
                        <dd className="inline">{campaign.organization.name}</dd>
                      </div>
                      <div>
                        <dt className="inline">Window: </dt>
                        <dd className="inline">
                          {formatDateRange(campaign.start_at, campaign.end_at)}
                        </dd>
                      </div>
                      <div>
                        <dt className="inline">Budget: </dt>
                        <dd className="inline">
                          {formatMoney(campaign.budget_amount, campaign.currency)}
                        </dd>
                      </div>
                      {submission ? (
                        <div>
                          <dt className="inline">Submitted: </dt>
                          <dd className="inline">{formatDate(submission.created_at)}</dd>
                        </div>
                      ) : null}
                    </dl>
                    <section className="border-edge mt-4 border-t pt-4" aria-label="Review history">
                      <h3 className="micro text-muted">Review history</h3>
                      {history.map((event) => (
                        <div key={event.id} className="mt-2 text-sm">
                          <StatusChip tone={statusTone[event.new_status]}>
                            {statusLabel[event.new_status]}
                          </StatusChip>
                          <span className="text-muted ml-2">
                            {statusLabel[event.prior_status]} → {statusLabel[event.new_status]}
                          </span>
                          {event.rejection_reason ? (
                            <p className="text-coral mt-1">Reason: {event.rejection_reason}</p>
                          ) : null}
                          {event.reviewed_snapshot_sha256 ? (
                            <p className="micro text-faint mt-1 font-mono break-all">
                              Snapshot SHA-256: {event.reviewed_snapshot_sha256}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </section>
                  </div>
                  <ReviewActions campaignId={campaign.id} />
                </div>
              </Panel>
            );
          })}
          {creativeItems.length ? (
            <h2 className="mt-4 text-lg font-medium">Managed creatives</h2>
          ) : null}
          {creativeItems.map(({ creative, campaign_name: campaignName, organization }) => {
            const history = historyByCreativeId.get(creative.id) ?? [];
            const submission = history.find((event) => event.new_status === "pending_review");
            return (
              <Panel
                key={creative.id}
                className="p-5"
                data-testid={`creative-approval-${creative.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusChip tone="amber">Pending review</StatusChip>
                      <h3 className="font-medium">{creative.name}</h3>
                    </div>
                    <dl className="micro text-faint mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">
                      <div>
                        <dt className="inline">Advertiser: </dt>
                        <dd className="inline">{organization.name}</dd>
                      </div>
                      <div>
                        <dt className="inline">Campaign: </dt>
                        <dd className="inline">{campaignName}</dd>
                      </div>
                      <div>
                        <dt className="inline">Type: </dt>
                        <dd className="inline">
                          {creative.creative_type} · {creative.placement}
                        </dd>
                      </div>
                      <div>
                        <dt className="inline">Validated MIME: </dt>
                        <dd className="inline">{creative.mime_type ?? "Unavailable"}</dd>
                      </div>
                      {submission ? (
                        <div>
                          <dt className="inline">Submitted: </dt>
                          <dd className="inline">{formatDate(submission.created_at)}</dd>
                        </div>
                      ) : null}
                    </dl>
                    {submission?.reviewed_snapshot_sha256 ? (
                      <p className="micro text-faint mt-3 font-mono break-all">
                        Snapshot SHA-256: {submission.reviewed_snapshot_sha256}
                      </p>
                    ) : null}
                  </div>
                  <CreativeReviewActions creativeId={creative.id} />
                </div>
              </Panel>
            );
          })}
          {installationItems.length ? (
            <h2 className="mt-4 text-lg font-medium">Vehicle installation evidence</h2>
          ) : null}
          {installationItems.map((evidence) => (
            <Panel
              key={evidence.id}
              className="p-5"
              data-testid={`installation-approval-${evidence.id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-5">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusChip tone="amber">Pending review</StatusChip>
                    <h3 className="font-medium">Installation revision {evidence.revision}</h3>
                  </div>
                  <dl className="micro text-faint mt-3 grid gap-x-5 gap-y-1 sm:grid-cols-2">
                    <div>
                      <dt className="inline">Assignment: </dt>
                      <dd className="inline font-mono">{evidence.assignment_id}</dd>
                    </div>
                    <div>
                      <dt className="inline">Vehicle: </dt>
                      <dd className="inline font-mono">{evidence.vehicle_id}</dd>
                    </div>
                    <div>
                      <dt className="inline">Captured: </dt>
                      <dd className="inline">{formatDate(evidence.captured_at)}</dd>
                    </div>
                    <div>
                      <dt className="inline">Submitted: </dt>
                      <dd className="inline">{formatDate(evidence.submitted_at)}</dd>
                    </div>
                  </dl>
                </div>
                <InstallationReviewActions submissionId={evidence.id} photos={evidence.photos} />
              </div>
            </Panel>
          ))}
        </div>
      )}
      <p className="micro text-faint mt-6">
        Approval records the reviewed submission only. Scheduling and activation remain unavailable.
      </p>
    </div>
  );
}
