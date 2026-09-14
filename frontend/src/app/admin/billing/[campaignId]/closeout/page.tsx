import Link from "next/link";
import { batchApi } from "../../../payouts/batches/batch-api";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import type { components } from "@/lib/api/schema";

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
  const position = await batchApi<components["schemas"]["CampaignMoneyPositionRead"]>(
    `/campaigns/${campaignId}/position?limit=25&offset=${page * 25}`,
  );
  return (
    <div className="mx-auto max-w-5xl space-y-5 pb-16">
      <Link className="underline" href={`/admin/billing/${campaignId}`}>
        Back to campaign billing
      </Link>
      <PageHeader title="Settlement and payout position" eyebrow={position.campaign_name} />
      <p className="text-muted">
        Recorded financial facts only. These records do not confirm physical removal, operational
        completion or an unverified transfer.
      </p>
      <p className="text-muted">
        Economic ledger totals count each credit once. Provider instructions and verified transfers
        are shown independently: late outcomes can leave additional exposure or duplicate transfers
        even after the credit is paid.
      </p>
      <Panel className="space-y-2 p-4">
        <h2 className="font-display text-xl">Cancellation</h2>
        {position.cancellation ? (
          <>
            <p>Cutoff: {formatDateTime(position.cancellation.cutoff_at)}</p>
            <p>{position.cancellation.disposition.replaceAll("_", " ")}</p>
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
                ["Earned net", item.earned_net],
                ["Available, unbatched", item.unbatched_available],
                ["Active reserved instructions", item.reserved],
                ["Unresolved provider exposure", item.in_flight],
                ["Verified failed", item.terminal_failed],
                ["Economic ledger paid", item.cash_paid],
                ["Verified provider transfers", item.provider_verified_paid],
                ["Driver-wide carry-forward debt (all campaigns)", item.driver_wide_debt],
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
            {settlement.disposition.replaceAll("_", " ")} ·{" "}
            {formatMoneyExact(settlement.amount, settlement.currency)}
          </p>
          <p>{formatDateTime(settlement.recorded_at)}</p>
        </Panel>
      ))}
      {!position.settlements.length ? <p>No settlement has been recorded on this page.</p> : null}
      {position.external_blockers.map((blocker) => (
        <p key={blocker} className="text-amber">
          {blocker}
        </p>
      ))}
      <nav aria-label="Money position pages" className="flex gap-4">
        {page > 0 ? <Link href={`?page=${page - 1}`}>Previous</Link> : null}
        <span>Page {page + 1}</span>
        {(page + 1) * 25 < Math.max(position.total, position.settlements_total) ? (
          <Link href={`?page=${page + 1}`}>Next</Link>
        ) : null}
      </nav>
    </div>
  );
}
