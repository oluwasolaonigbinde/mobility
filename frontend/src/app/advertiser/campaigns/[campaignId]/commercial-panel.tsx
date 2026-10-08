"use client";

import { useActionState } from "react";
import { formatMoney } from "@/lib/format";
import type { components } from "@/lib/api/schema";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { CommercialHistory } from "@/lib/billing/commercial-history";
import {
  acceptExpeditedWaiverAction,
  acceptQuoteAction,
  requestQuoteAction,
  type CommercialActionState,
} from "./commercial-actions";

type Commercial = components["schemas"]["CampaignCommercialRead"];
type Quotation = Commercial["revisions"][number] | NonNullable<Commercial["terms"]>;

const initialState: CommercialActionState = {};

const budgetStateLabel: Record<string, string> = {
  blocked_external_policy: "Not set up yet",
  within_budget: "Within budget",
  alert_threshold: "Warning: most of the budget is used",
  urgent_threshold: "Urgent: the budget is nearly used",
  pause_threshold: "Paused: the budget is used up",
};

function exactMoney(currency: string, amount: string | number) {
  return formatMoney(amount, currency);
}

function termLabel(key: string) {
  const words = key.replaceAll("_", " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
}

/**
 * Render recorded quotation terms completely and readably: every key (as a
 * readable label) and every value is shown, nothing is summarised, and nesting
 * is preserved.
 */
function TermsValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <>Not specified</>;
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <>None</>;
    return (
      <ul className="list-disc pl-4">
        {value.map((item, index) => (
          <li key={index}>
            <TermsValue value={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <>None</>;
    return (
      <dl className="grid gap-1.5">
        {entries.map(([key, item]) => (
          <div key={key}>
            <dt className="text-faint text-xs">{termLabel(key)}</dt>
            <dd className="text-sm">
              <TermsValue value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <>{String(value)}</>;
}

function QuotationFacts({ quotation, accepted }: { quotation: Quotation; accepted: boolean }) {
  const revisionNumber =
    "revision_number" in quotation
      ? quotation.revision_number
      : quotation.quotation_revision_number;
  return (
    <div
      className="border-edge mt-4 rounded-lg border p-4"
      aria-label={accepted ? "Accepted quotation receipt" : "Latest quotation for review"}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">
            {quotation.quote_reference} · revision {revisionNumber}
          </p>
          <p className="micro text-muted mt-1">
            {accepted ? "Accepted quotation receipt" : "Latest quotation for review"}
          </p>
        </div>
        {accepted ? <StatusChip tone="green">Accepted and fixed</StatusChip> : null}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="micro text-muted">
            <tr>
              <th className="pb-2 font-normal">Item</th>
              <th className="pb-2 font-normal">Kind</th>
              <th className="pb-2 text-right font-normal">Exact amount</th>
            </tr>
          </thead>
          <tbody className="divide-edge/60 divide-y">
            {quotation.line_items.map((item, index) => (
              <tr key={`${String(item.code)}:${index}`}>
                <td className="py-2 pr-3">
                  <span className="font-medium">{String(item.description)}</span>
                  <span className="text-faint ml-2 font-mono text-xs">{String(item.code)}</span>
                </td>
                <td className="py-2 pr-3">{String(item.kind)}</td>
                <td className="py-2 text-right font-mono text-xs">
                  {exactMoney(quotation.currency, String(item.amount))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="border-edge mt-4 grid gap-3 border-t pt-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="micro text-muted">Production cost</dt>
          <dd className="mt-1 font-mono text-xs">
            {exactMoney(quotation.currency, quotation.production_cost_amount)}
          </dd>
        </div>
        <div>
          <dt className="micro text-muted">Net</dt>
          <dd className="mt-1 font-mono text-xs">
            {exactMoney(quotation.currency, quotation.net_amount)}
          </dd>
        </div>
        <div>
          <dt className="micro text-muted">Included VAT</dt>
          <dd className="mt-1 font-mono text-xs">
            VAT {Number(quotation.tax_rate) * 100}% ·{" "}
            {exactMoney(quotation.currency, quotation.tax_amount)}
          </dd>
        </div>
        <div>
          <dt className="micro text-muted">VAT-inclusive total</dt>
          <dd className="mt-1 font-mono text-xs">
            {exactMoney(quotation.currency, quotation.gross_amount)}
          </dd>
        </div>
      </dl>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <div>
          <p className="micro text-muted">Payment arrangement</p>
          <p className="mt-1 text-sm">{quotation.payment_class.replaceAll("_", " ")}</p>
        </div>
        <div>
          <p className="micro text-muted">Production scope</p>
          <div className="mt-1 break-words">
            <TermsValue value={quotation.production_scope} />
          </div>
        </div>
        <div>
          <p className="micro text-muted">Payment dates and conditions</p>
          <div className="mt-1 break-words">
            {Object.keys(quotation.payment_terms).length ? (
              <TermsValue value={quotation.payment_terms} />
            ) : (
              "No additional conditions recorded"
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function CommercialPanel({
  campaignId,
  commercial,
  error,
  canRequestQuotation = true,
}: {
  campaignId: string;
  commercial: Commercial;
  error?: string;
  canRequestQuotation?: boolean;
}) {
  const latest = commercial.revisions.at(-1);
  const [requestState, requestAction, requesting] = useActionState(
    requestQuoteAction,
    initialState,
  );
  const [acceptState, acceptAction, accepting] = useActionState(acceptQuoteAction, initialState);
  const [waiverState, waiverAction, waiving] = useActionState(
    acceptExpeditedWaiverAction,
    initialState,
  );
  const acceptedTerms = commercial.terms ?? acceptState.acceptedTerms;
  return (
    <>
      <Panel className="mt-6 p-6">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-semibold">Commercial terms</h2>
            <p className="micro text-muted mt-1">Your quotation, payment and production status</p>
          </div>
          <StatusChip tone={acceptedTerms ? "green" : latest ? "amber" : "default"}>
            {acceptedTerms
              ? "Accepted"
              : latest
                ? "Awaiting acceptance"
                : commercial.quote_request
                  ? "In review"
                  : "Not requested"}
          </StatusChip>
        </div>
        {error ? <p className="text-coral mb-4 text-sm">{error}</p> : null}
        {[requestState, acceptState, waiverState].map((state, index) =>
          state.error || state.done ? (
            <p
              key={index}
              role={state.error ? "alert" : "status"}
              className={`${state.error ? "text-coral" : "text-green"} mb-4 text-sm`}
            >
              {state.error ?? `✓ ${state.done}`}
            </p>
          ) : null,
        )}
        {canRequestQuotation && !commercial.quote_request && !requestState.done ? (
          <form action={requestAction} className="flex flex-col gap-3 sm:flex-row">
            <input type="hidden" name="campaign_id" value={campaignId} />
            <input
              name="notes"
              aria-label="Quotation notes"
              placeholder="Vehicle count, timing or production notes"
              className="border-edge bg-raised h-11 flex-1 rounded-lg border px-3.5 text-sm"
            />
            <Button type="submit" disabled={requesting}>
              {requesting ? "Requesting…" : "Request custom quotation"}
            </Button>
          </form>
        ) : null}
        {acceptedTerms ? (
          <QuotationFacts quotation={acceptedTerms} accepted />
        ) : latest ? (
          <>
            <QuotationFacts quotation={latest} accepted={false} />
            <form action={acceptAction} className="border-edge mt-4 border-t pt-4">
              <input type="hidden" name="campaign_id" value={campaignId} />
              <input type="hidden" name="revision_id" value={latest.id} />
              <label className="flex items-start gap-3 text-sm">
                <input type="checkbox" name="confirmed" required className="mt-1" />
                <span>
                  I reviewed the scope, every line item, production cost, tax, exact total, payment
                  arrangement, dates and conditions for revision {latest.revision_number}.
                </span>
              </label>
              <Button type="submit" className="mt-3" disabled={accepting}>
                {accepting ? "Accepting…" : "Accept these exact terms"}
              </Button>
            </form>
          </>
        ) : commercial.quote_request ? (
          <p className="text-muted text-sm">
            Your request has been received. Our team will prepare a quotation for you to review
            here.
          </p>
        ) : null}
        {acceptedTerms ? (
          <div className="border-edge mt-5 grid gap-4 border-t pt-5 md:grid-cols-3">
            <div>
              <p className="micro text-muted">Payment basis</p>
              <p className="mt-1 text-sm">
                {commercial.financial_authority
                  ? `${commercial.financial_authority.authority_type.replaceAll("_", " ")} · ${formatMoney(commercial.financial_authority.authorized_amount, commercial.financial_authority.currency)}`
                  : "Pending"}
              </p>
            </div>
            <div>
              <p className="micro text-muted">Production</p>
              <p className="mt-1 text-sm">
                {commercial.production_start
                  ? `Started · ${commercial.production_start.authority_basis.replaceAll("_", " ")}`
                  : "Not authorised to start"}
              </p>
            </div>
            <div>
              <p className="micro text-muted">Budget alerts</p>
              <p className="mt-1 text-sm">
                {budgetStateLabel[commercial.budget_evaluations.at(-1)?.state ?? ""] ??
                  "Not checked yet"}
              </p>
            </div>
          </div>
        ) : null}
        {commercial.terms?.payment_class === "standard_prepaid" &&
        !commercial.waiver &&
        !commercial.production_start ? (
          <form action={waiverAction} className="border-edge mt-5 border-t pt-5">
            <input type="hidden" name="campaign_id" value={campaignId} />
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" required className="mt-1" />
              <span>{commercial.expedited_waiver_copy.accepted_wording}</span>
            </label>
            <input
              type="hidden"
              name="wording_version"
              value={commercial.expedited_waiver_copy.wording_version}
            />
            <input
              type="hidden"
              name="accepted_wording"
              value={commercial.expedited_waiver_copy.accepted_wording}
            />
            <input
              type="hidden"
              name="accepted_wording_hash"
              value={commercial.expedited_waiver_copy.accepted_wording_hash}
            />
            <Button type="submit" variant="ghost" className="mt-3" disabled={waiving}>
              {waiving ? "Recording…" : "Record expedited waiver"}
            </Button>
          </form>
        ) : null}
      </Panel>
      <CommercialHistory invoices={commercial.invoices} settlements={commercial.settlements} />
    </>
  );
}
