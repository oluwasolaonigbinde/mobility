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

export const metadata: Metadata = { title: "Campaign approvals" };

const PAGE_SIZE = 25;

export default async function AdminApprovalsPage() {
  const api = createApiClient(await getSessionToken());
  const { data: queue } = await api.GET("/api/v1/admin/campaigns/pending-review", {
    params: { query: { limit: PAGE_SIZE, offset: 0 } },
  });
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

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Campaign approvals"
        eyebrow={`${queue?.total ?? 0} campaign${queue?.total === 1 ? "" : "s"} awaiting review`}
      />

      {items.length === 0 ? (
        <EmptyState
          title="No campaigns awaiting review"
          body="New submissions will appear here with their immutable review history."
        />
      ) : (
        <div className="flex flex-col gap-4">
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
        </div>
      )}
      <p className="micro text-faint mt-6">
        Approval records the reviewed submission only. Scheduling and activation remain unavailable.
      </p>
    </div>
  );
}
