import { formatMoney } from "@/lib/format";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { acceptQuoteAction, requestQuoteAction } from "./commercial-actions";

type Commercial = components["schemas"]["CampaignCommercialRead"];

export function CommercialPanel({
  campaignId,
  commercial,
  error,
}: {
  campaignId: string;
  commercial: Commercial;
  error?: string;
}) {
  const latest = commercial.revisions.at(-1);
  const requestAction = requestQuoteAction.bind(null, campaignId);
  const acceptAction = latest ? acceptQuoteAction.bind(null, campaignId, latest.id) : undefined;
  return (
    <Panel className="mt-6 p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold">Commercial terms</h2>
          <p className="micro text-muted mt-1">Immutable quotation, funding and production facts</p>
        </div>
        <StatusChip tone={commercial.terms ? "green" : latest ? "amber" : "default"}>
          {commercial.terms ? "Accepted" : latest ? "Awaiting acceptance" : commercial.quote_request ? "In review" : "Not requested"}
        </StatusChip>
      </div>
      {error ? <p className="text-coral mb-4 text-sm">{error}</p> : null}
      {!commercial.quote_request ? (
        <form action={requestAction} className="flex flex-col gap-3 sm:flex-row">
          <input
            name="notes"
            aria-label="Quotation notes"
            placeholder="Vehicle count, timing or production notes"
            className="border-edge bg-raised h-11 flex-1 rounded-lg border px-3.5 text-sm"
          />
          <Button type="submit">Request custom quotation</Button>
        </form>
      ) : null}
      {latest ? (
        <div className="border-edge mt-4 rounded-lg border p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">{latest.quote_reference} · revision {latest.revision_number}</p>
              <p className="micro text-muted mt-1">
                {formatMoney(latest.net_amount, latest.currency)} net + {formatMoney(latest.tax_amount, latest.currency)} VAT · {formatMoney(latest.gross_amount, latest.currency)} total
              </p>
            </div>
            {!commercial.terms && acceptAction ? (
              <form action={acceptAction}>
                <Button type="submit">Accept immutable terms</Button>
              </form>
            ) : null}
          </div>
        </div>
      ) : commercial.quote_request ? (
        <p className="text-muted text-sm">Your request is recorded. Operations will add a structured revision.</p>
      ) : null}
    </Panel>
  );
}
