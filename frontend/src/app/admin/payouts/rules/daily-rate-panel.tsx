"use client";

import { useActionState, useId } from "react";
import { publishDailyRateAction, type DailyRateActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { formatDateTime, formatMoneyExact } from "@/lib/format";
import type { components } from "@/lib/api/schema";

type Revision = components["schemas"]["CampaignPayoutRuleRevisionRead"];

const initialState: DailyRateActionState = {};

function shorterDays(revision: Revision): string {
  if (revision.shortfall_strategy === "per_mile_deduction") {
    return `${formatMoneyExact(revision.deduction_per_mile_naira)} off per missing mile`;
  }
  return "In proportion to miles";
}

function outsideArea(weight: string | null | undefined): string {
  const share = Number(weight);
  if (share >= 1) return "Count in full";
  if (share <= 0) return "Not counted";
  return `Count at ${Math.round(share * 1000) / 10}%`;
}

/**
 * D39 daily-rate pay (payout_v4). Values are append-only revisions entered by
 * Terrax Media staff; the 5-minute stop rule is fixed by Cardvert. Publishing
 * stays switched off until the client confirms the shortfall rule, which miles
 * count and the cap.
 */
export function DailyRatePanel({
  campaignId,
  revisions,
  publishingEnabled,
}: {
  campaignId: string;
  revisions: Revision[];
  publishingEnabled: boolean;
}) {
  const [state, formAction, pending] = useActionState(publishDailyRateAction, initialState);
  const strategyId = useId();
  const notSwitchedOn = !publishingEnabled || state.notSwitchedOn;
  const fieldError = (name: string) => (state.field === name ? state.error : undefined);
  const previous = (name: string) => (state.created ? "" : (state.values?.[name] ?? ""));

  return (
    <div className="flex flex-col gap-6">
      {notSwitchedOn ? (
        <p
          role="status"
          className="border-amber/40 bg-amber/10 text-amber rounded-lg border px-3.5 py-2.5 text-sm"
        >
          Daily-rate pay is not switched on yet. It opens once the client confirms how shorter days
          are paid, which miles count and the full-day amount.
        </p>
      ) : null}

      <form action={formAction} className="flex flex-col gap-6" noValidate>
        <input type="hidden" name="campaign_id" value={campaignId} />
        <fieldset className="grid gap-4 sm:grid-cols-2" disabled={notSwitchedOn || pending}>
          <legend className="micro text-muted mb-3">New revision — daily rate (NGN)</legend>
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
          <div className="flex flex-col gap-1.5">
            <label htmlFor={strategyId} className="micro text-muted">
              Shorter days are paid
            </label>
            <select
              id={strategyId}
              name="shortfall_strategy"
              defaultValue={previous("shortfall_strategy")}
              aria-invalid={fieldError("shortfall_strategy") ? true : undefined}
              className="bg-raised text-ink border-edge focus:border-amber h-11 rounded-lg border px-3.5 text-sm focus:outline-none"
            >
              <option value="" disabled>
                Choose…
              </option>
              <option value="proportional">In proportion to the miles covered</option>
              <option value="per_mile_deduction">
                Day rate minus a fixed amount per missing mile
              </option>
            </select>
            {fieldError("shortfall_strategy") ? (
              <p role="alert" className="text-coral text-xs">
                {fieldError("shortfall_strategy")}
              </p>
            ) : null}
          </div>
          <Field
            label="Deduction per missing mile (₦, per-mile rule only)"
            name="deduction_per_mile_naira"
            defaultValue={previous("deduction_per_mile_naira")}
            inputMode="decimal"
            className="font-mono"
            error={fieldError("deduction_per_mile_naira")}
          />
          <Field
            label="Minimum miles for any pay (0 for none)"
            name="minimum_miles"
            defaultValue={previous("minimum_miles")}
            inputMode="decimal"
            className="font-mono"
            error={fieldError("minimum_miles")}
          />
          <Field
            label="Share of miles outside the campaign area that count (0 to 1)"
            name="outside_area_weight"
            defaultValue={previous("outside_area_weight")}
            inputMode="decimal"
            className="font-mono"
            error={fieldError("outside_area_weight")}
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
            label="Reason (audited)"
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

        <Button type="submit" disabled={notSwitchedOn || pending} className="w-full">
          {pending ? "Publishing…" : "Publish daily rate"}
        </Button>
        <p className="micro text-faint">
          Stops of up to 5 minutes count as driving; longer stops add no miles (fixed by Cardvert).
          Drivers keep the terms they accepted; past days change only through a correction.
        </p>
      </form>

      <div>
        <h3 className="micro text-muted mb-3">Revision history</h3>
        {revisions.length === 0 ? (
          <p className="text-muted text-sm">No pay revisions for this campaign yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-edge micro text-muted border-b text-left">
                  <th className="py-2 pr-4 font-normal">#</th>
                  <th className="px-4 py-2 font-normal">Starts</th>
                  <th className="px-4 py-2 text-right font-normal">Day rate</th>
                  <th className="px-4 py-2 text-right font-normal">Daily miles</th>
                  <th className="px-4 py-2 font-normal">Shorter days</th>
                  <th className="px-4 py-2 text-right font-normal">Minimum</th>
                  <th className="px-4 py-2 font-normal">Outside area</th>
                  <th className="py-2 pl-4 font-normal">Reason</th>
                </tr>
              </thead>
              <tbody>
                {revisions.map((r) => (
                  <tr key={r.id} className="border-edge/60 border-b text-xs last:border-0">
                    <td className="py-3 pr-4 font-mono">r{r.revision_number}</td>
                    <td className="px-4 py-3 font-mono">{formatDateTime(r.effective_from)}</td>
                    {r.formula_version === "payout_v4" ? (
                      <>
                        <td className="px-4 py-3 text-right font-mono">
                          {formatMoneyExact(r.daily_rate_naira)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {Number(r.daily_target_miles)}
                        </td>
                        <td className="px-4 py-3">{shorterDays(r)}</td>
                        <td className="px-4 py-3 text-right font-mono">
                          {Number(r.minimum_miles)}
                        </td>
                        <td className="px-4 py-3">{outsideArea(r.outside_area_weight)}</td>
                      </>
                    ) : (
                      <td className="text-muted px-4 py-3" colSpan={5}>
                        Earlier hourly terms: {formatMoneyExact(r.hourly_rate_naira)}/hour
                      </td>
                    )}
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
