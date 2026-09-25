"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { updateCampaignDetailsAction, type CampaignEditState } from "../actions";

export interface CampaignEditDefaults {
  name: string;
  description: string;
  start_at: string;
  end_at: string;
  budget_amount: string;
  daily_budget_amount: string;
}

const initialState: CampaignEditState = {};

export function CampaignEditForm({
  campaignId,
  currency,
  defaults,
}: {
  campaignId: string;
  currency: string;
  defaults: CampaignEditDefaults;
}) {
  const [state, formAction, pending] = useActionState(updateCampaignDetailsAction, initialState);
  // React resets the form after each action; a failed save re-renders the
  // submitted values so the advertiser's edits survive the error.
  const shown = { ...defaults, ...state.values };

  return (
    <form action={formAction} className="flex max-w-xl flex-col gap-5">
      <input type="hidden" name="campaign_id" value={campaignId} />
      {Object.entries(defaults).map(([field, value]) => (
        <input key={field} type="hidden" name={`original_${field}`} value={value} />
      ))}
      <Field label="Campaign name" name="name" defaultValue={shown.name} required />
      <label className="flex flex-col gap-1.5">
        <span className="micro text-muted">Description</span>
        <textarea
          name="description"
          rows={3}
          defaultValue={shown.description}
          className="border-edge bg-raised text-ink focus:border-amber rounded-lg border px-3.5 py-2.5 text-sm focus:outline-none"
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Starts (Lagos time)"
          name="start_at"
          type="datetime-local"
          defaultValue={shown.start_at}
        />
        <Field
          label="Ends (Lagos time)"
          name="end_at"
          type="datetime-local"
          defaultValue={shown.end_at}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={`Total budget (${currency})`}
          name="budget_amount"
          inputMode="decimal"
          defaultValue={shown.budget_amount}
        />
        <Field
          label={`Daily budget (${currency})`}
          name="daily_budget_amount"
          inputMode="decimal"
          defaultValue={shown.daily_budget_amount}
        />
      </div>
      {state.error ? (
        <p role="alert" className="text-coral text-sm">
          {state.error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save changes"}
        </Button>
        <Link href={`/advertiser/campaigns/${campaignId}`} className="text-muted text-sm underline">
          Cancel
        </Link>
      </div>
      <p className="micro text-muted">
        Saving keeps the campaign in its current status. Submit it for review from the campaign page
        when it is ready.
      </p>
    </form>
  );
}
