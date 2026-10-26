"use client";

import { useActionState } from "react";
import { publishDailyRateAction, type DailyRateActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import type { components } from "@/lib/api/schema";

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

const initialState: DailyRateActionState = {};

export function DailyRatePanel({
  campaignId,
  revisions,
}: {
  campaignId: string;
  revisions: Revision[];
}) {
  const [state, formAction, pending] = useActionState(publishDailyRateAction, initialState);
  const fieldError = (name: string) => (state.field === name ? state.error : undefined);
  const previous = (name: string) => (state.created ? "" : (state.values?.[name] ?? ""));

  return (
    <div className="flex flex-col gap-6">
      <form action={formAction} className="flex flex-col gap-6" noValidate>
        <input type="hidden" name="campaign_id" value={campaignId} />
        <fieldset className="grid gap-4 sm:grid-cols-2" disabled={pending}>
          <legend className="micro text-muted mb-3">New version — daily rate (NGN)</legend>
          <Field
            label="Day rate (₦)"
            name="daily_rate_naira"
            defaultValue={previous("daily_rate_naira")}
            inputMode="decimal"
            className="font-mono"
            error={fieldError("daily_rate_naira")}
          />
          <Field
            label="Daily miles for a full day"
            name="daily_target_miles"
            defaultValue={previous("daily_target_miles")}
            inputMode="decimal"
            className="font-mono"
            error={fieldError("daily_target_miles")}
          />
          <Field
            label="Starts (future)"
            name="effective_from"
            defaultValue={previous("effective_from")}
            type="datetime-local"
            className="font-mono"
            error={fieldError("effective_from")}
          />
          <Field
            label="Reason"
            name="reason"
            defaultValue={previous("reason")}
            placeholder="for example: on-request areas"
            error={fieldError("reason")}
          />
        </fieldset>

        {state.error && !state.field ? (
          <p
            role="alert"
            className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
          >
            {state.error}
          </p>
        ) : null}
        {state.created && !state.error ? (
          <p className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm">
            ✓ Daily rate published — offers made from its start time use these terms.
          </p>
        ) : null}

        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Publishing…" : "Publish daily rate"}
        </Button>
        <p className="micro text-faint">
          Only in-area miles count, with no minimum. Shorter days earn a proportional share up to
          the day rate. Stops of up to 5 minutes count as driving; longer stops add no miles (fixed
          by Cardvert). Drivers keep the terms they accepted; past days change only through a
          correction.
        </p>
      </form>

      <div>
        <h3 className="micro text-muted mb-3">Version history</h3>
        {revisions.length === 0 ? (
          <p className="text-muted text-sm">No pay versions for this campaign yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-edge micro text-muted border-b text-left">
                  <th className="py-2 pr-4 font-normal">#</th>
                  <th className="px-4 py-2 font-normal">Starts</th>
                  <th className="px-4 py-2 text-right font-normal">Day rate</th>
                  <th className="px-4 py-2 text-right font-normal">Daily miles</th>
                  <th className="py-2 pl-4 font-normal">Reason</th>
                </tr>
              </thead>
              <tbody>
                {revisions.map((r) => (
                  <tr key={r.id} className="border-edge/60 border-b text-xs last:border-0">
                    <td className="py-3 pr-4 font-mono">Version {r.revision_number}</td>
                    <td className="px-4 py-3 font-mono">{formatDateTime(r.effective_from)}</td>
                    <td className="px-4 py-3 text-right font-mono">
                      {formatMoneyExact(r.daily_rate_naira)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {Number(r.daily_target_miles)}
                    </td>
                    <td className="text-muted max-w-[14rem] truncate py-3 pl-4" title={r.reason}>
                      {r.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
