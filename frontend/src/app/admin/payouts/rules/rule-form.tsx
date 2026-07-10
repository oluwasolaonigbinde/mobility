"use client";

import { useActionState } from "react";
import { saveRuleAction, type RuleActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import type { components } from "@/lib/api/schema";

type Rule = components["schemas"]["CampaignPayoutRuleRead"];

const initialState: RuleActionState = {};

export function RuleForm({ campaignId, rule }: { campaignId: string; rule: Rule | null }) {
  const [state, formAction, pending] = useActionState(saveRuleAction, initialState);

  const d = (v: string | null | undefined) => v ?? "";

  return (
    <form
      key={`${campaignId}:${rule?.id ?? "new"}`}
      action={formAction}
      className="flex flex-col gap-6"
      noValidate
    >
      <input type="hidden" name="campaign_id" value={campaignId} />
      {rule ? <input type="hidden" name="rule_id" value={rule.id} /> : null}

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="micro text-muted mb-3">Base rates (NGN)</legend>
        <Field
          label="Per km"
          name="base_rate_per_km"
          inputMode="decimal"
          defaultValue={d(rule?.base_rate_per_km)}
          placeholder="e.g. 55"
          className="font-mono"
        />
        <Field
          label="Per active hour"
          name="base_rate_per_active_hour"
          inputMode="decimal"
          defaultValue={d(rule?.base_rate_per_active_hour)}
          placeholder="e.g. 120"
          className="font-mono"
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-3">
        <legend className="micro text-muted mb-3">Zone & exposure bonuses</legend>
        <Field
          label="Target zone /km"
          name="target_zone_bonus_rate_per_km"
          inputMode="decimal"
          defaultValue={d(rule?.target_zone_bonus_rate_per_km)}
          placeholder="e.g. 25"
          className="font-mono"
        />
        <Field
          label="Bonus zone /km"
          name="bonus_zone_bonus_rate_per_km"
          inputMode="decimal"
          defaultValue={d(rule?.bonus_zone_bonus_rate_per_km)}
          placeholder="e.g. 15"
          className="font-mono"
        />
        <Field
          label="Per 1,000 impressions"
          name="estimated_impression_rate_per_1000"
          inputMode="decimal"
          defaultValue={d(rule?.estimated_impression_rate_per_1000)}
          placeholder="e.g. 80"
          className="font-mono"
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="micro text-muted mb-3">Per-trip caps (NGN)</legend>
        <Field
          label="Minimum"
          name="min_payout_per_trip"
          inputMode="decimal"
          defaultValue={d(rule?.min_payout_per_trip)}
          placeholder="e.g. 1500"
          className="font-mono"
        />
        <Field
          label="Maximum"
          name="max_payout_per_trip"
          inputMode="decimal"
          defaultValue={d(rule?.max_payout_per_trip)}
          placeholder="e.g. 10000"
          className="font-mono"
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-3">
        <legend className="micro text-muted mb-3">
          Fraud multipliers (0–1 · applied by flag severity)
        </legend>
        <Field
          label="Low severity"
          name="low_fraud_multiplier"
          inputMode="decimal"
          defaultValue={d(rule?.low_fraud_multiplier)}
          placeholder="0.90"
          className="font-mono"
        />
        <Field
          label="Medium severity"
          name="medium_fraud_multiplier"
          inputMode="decimal"
          defaultValue={d(rule?.medium_fraud_multiplier)}
          placeholder="0.70"
          className="font-mono"
        />
        <Field
          label="High severity"
          name="high_fraud_multiplier"
          inputMode="decimal"
          defaultValue={d(rule?.high_fraud_multiplier)}
          placeholder="0.25"
          className="font-mono"
        />
      </fieldset>

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      {state.saved && !state.error ? (
        <p className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm">
          ✓ Rule saved — new trips on this campaign pay under these terms.
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : rule ? "Update rule" : "Create rule"}
      </Button>
      <p className="micro text-faint">
        Empty fields fall back to platform defaults. Already-calculated payouts are never rewritten
        — rules apply from the next calculation onward.
      </p>
    </form>
  );
}
