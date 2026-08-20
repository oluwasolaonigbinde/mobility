"use client";

import { useActionState } from "react";
import { createRevisionAction, type RevisionActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import type { components } from "@/lib/api/schema";

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

const initialState: RevisionActionState = {};

/**
 * Hourly-rule value chain (MNY-06A): rates are immutable once written — the
 * only value change is appending a future-dated revision. The list arrives
 * newest-first from the API (capped at 50 by the page).
 */
export function RevisionsPanel({
  campaignId,
  ruleId,
  revisions,
}: {
  campaignId: string;
  ruleId: string;
  revisions: Revision[];
}) {
  const [state, formAction, pending] = useActionState(createRevisionAction, initialState);
  const latest = revisions[0];

  return (
    <div className="flex flex-col gap-6">
      <form
        key={`${campaignId}:${latest?.id ?? "genesis"}`}
        action={formAction}
        className="flex flex-col gap-6"
        noValidate
      >
        <input type="hidden" name="campaign_id" value={campaignId} />
        <input type="hidden" name="rule_id" value={ruleId} />

        <fieldset className="grid gap-4 sm:grid-cols-3">
          <legend className="micro text-muted mb-3">New revision — hourly pay (NGN)</legend>
          <Field
            label="Base hourly rate"
            name="hourly_rate_naira"
            inputMode="decimal"
            defaultValue={latest?.hourly_rate_naira ?? ""}
            placeholder="e.g. 1200"
            className="font-mono"
          />
          <Field
            label="Premium hourly rate (optional)"
            name="premium_hourly_rate_naira"
            inputMode="decimal"
            defaultValue={latest?.premium_hourly_rate_naira ?? ""}
            placeholder="e.g. 1500"
            className="font-mono"
          />
          <Field
            label="Daily payable-hours cap"
            name="daily_payable_hours_cap"
            inputMode="decimal"
            defaultValue={latest?.daily_payable_hours_cap ?? ""}
            placeholder="e.g. 8"
            className="font-mono"
          />
        </fieldset>

        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="micro text-muted mb-3">Takes effect</legend>
          <Field
            label="Effective from (future)"
            name="effective_from"
            type="datetime-local"
            className="font-mono"
          />
          <Field label="Reason (audited)" name="reason" placeholder="why the rates change" />
        </fieldset>

        {state.error ? (
          <p
            role="alert"
            className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
          >
            {state.error}
          </p>
        ) : null}
        {state.created && !state.error ? (
          <p className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm">
            ✓ Revision created — trips accepted from its effective time pay under these terms.
          </p>
        ) : null}

        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Creating…" : "Create revision"}
        </Button>
        <p className="micro text-faint">
          Rule values are immutable — each change appends a future-dated revision. Drivers keep the
          terms frozen at acceptance; retroactive changes go through a correction order.
        </p>
      </form>

      <div>
        <h3 className="micro text-muted mb-3">Revision history</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="py-2 pr-4 font-normal">#</th>
                <th className="px-4 py-2 font-normal">Effective from</th>
                <th className="px-4 py-2 text-right font-normal">Base /h</th>
                <th className="px-4 py-2 text-right font-normal">Premium /h</th>
                <th className="px-4 py-2 text-right font-normal">Daily cap</th>
                <th className="px-4 py-2 font-normal">Reason</th>
                <th className="py-2 pl-4 font-normal">Creator</th>
              </tr>
            </thead>
            <tbody>
              {revisions.map((r) => (
                <tr key={r.id} className="border-edge/60 border-b font-mono text-xs last:border-0">
                  <td className="py-3 pr-4">r{r.revision_number}</td>
                  <td className="px-4 py-3">{formatDateTime(r.effective_from)}</td>
                  <td className="px-4 py-3 text-right">{formatMoneyExact(r.hourly_rate_naira)}</td>
                  <td className="px-4 py-3 text-right">
                    {formatMoneyExact(r.premium_hourly_rate_naira)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {r.daily_payable_hours_cap ? `${r.daily_payable_hours_cap}h` : "—"}
                  </td>
                  <td className="text-muted max-w-[16rem] truncate px-4 py-3" title={r.reason}>
                    {r.reason}
                  </td>
                  <td className="text-muted py-3 pl-4">{r.created_by_user_id.slice(0, 8)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
