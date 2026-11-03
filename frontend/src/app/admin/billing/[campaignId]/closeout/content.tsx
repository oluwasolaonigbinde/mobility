import { adminValueFailure } from "@/lib/api/admin-read";
import Link from "next/link";
import { batchApi } from "../../../payouts/batches/batch-api";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import type { components } from "@/lib/api/schema";
import { adminStatus } from "@/lib/status/admin";
import { QueueUnavailable } from "../../../queue-search";

export default async function MoneyCloseoutPage({
  params,
  searchParams,
}: {
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const { campaignId } = await params;
  const query = await searchParams;
  const page = /^\d+$/.test(query.page ?? "") ? Math.min(Number(query.page), 100000) : 0;
  let position;
  try {
    position = await batchApi<components["schemas"]["CampaignMoneyPositionRead"]>(
      `/campaigns/${campaignId}/position?limit=25&offset=${page * 25}`,
    );
  } catch (error) {
    adminValueFailure(error);
    return <QueueUnavailable />;
  }
  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-16">
      <Link className="underline" href={`/admin/campaigns/${campaignId}#money`}>
        Back to campaign Money
      </Link>
      <PageHeader title="Money summary" eyebrow={position.campaign_name} />
      <Panel className="space-y-2 p-4">
        <h2 className="font-display text-xl">Cancellation</h2>
        {position.cancellation ? (
          <>
            <p>Cutoff: {formatDateTime(position.cancellation.cutoff_at)}</p>
            <p>{adminStatus(position.cancellation.disposition, "cancellation")}</p>
            <p>
              Recorded refundable amount:{" "}
              {formatMoneyExact(
                position.cancellation.refundable_amount,
                position.cancellation.currency,
              )}
            </p>
          </>
        ) : (
          <p>No cancellation has been recorded.</p>
        )}
      </Panel>
      <h2 className="font-display text-xl">Campaign earnings by driver</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {position.items.map((item) => (
          <Panel key={`${item.driver_profile_id}:${item.currency}`} className="space-y-2 p-4">
            <h3 className="font-semibold">
              {item.driver_name} · {item.currency}
            </h3>
            {(
              [
                ["Earned", item.earned_net],
                ["Ready to pay", item.unbatched_available],
                ["Saved, not sent yet", item.reserved],
                ["Waiting for a payment result", item.in_flight],
                ["Failed payments", item.terminal_failed],
                ["Cash paid", item.cash_paid],
                ["Transfers paid", item.provider_verified_paid],
              ] as const
            ).map(([label, amount]) => (
              <p key={label} className="text-sm">
                {label}: {formatMoneyExact(amount, item.currency)}
              </p>
            ))}
          </Panel>
        ))}
      </div>
      {!position.items.length ? <p>No campaign earnings on this page.</p> : null}
      <h2 className="font-display text-xl">Recorded settlements</h2>
      {position.settlements.map((settlement) => (
        <Panel key={settlement.id} className="p-4">
          <p>
            {adminStatus(settlement.disposition, "settlement")} ·{" "}
            {formatMoneyExact(settlement.amount, settlement.currency)}
          </p>
          <p>{formatDateTime(settlement.recorded_at)}</p>
        </Panel>
      ))}
      {!position.settlements.length ? <p>No settlement has been recorded on this page.</p> : null}
      <nav aria-label="Money position pages" className="flex gap-4">
        {page > 0 ? (
          <Link href={`/admin/campaigns/${campaignId}?drawer=closeout&page=${page - 1}#money`}>
            Previous
          </Link>
        ) : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < Math.max(position.total, position.settlements_total) ? (
          <Link href={`/admin/campaigns/${campaignId}?drawer=closeout&page=${page + 1}#money`}>
            Next
          </Link>
        ) : null}
      </nav>
    </div>
  );
}
