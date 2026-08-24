"use client";

import { useActionState, useState } from "react";
import { saveRuleAction, type RuleActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { cx } from "@/lib/cx";
import type { PayoutModel } from "@/lib/payouts/schema";
import type { components } from "@/lib/api/schema";

type Rule = components["schemas"]["CampaignPayoutRuleRead"];

const initialState: RuleActionState = {};

const MODEL_OPTIONS: { value: PayoutModel; label: string; hint: string }[] = [
  {
    value: "payout_v2",
    label: "Hourly + daily cap",
    hint: "hourly rate × GPS-verified time, capped per driver per day",
  },
  {
    value: "payout_v1",
    label: "Legacy per-km",
    hint: "component rates: distance, active time, zones, impressions",
  },
];

export function RuleForm({ campaignId, rule }: { campaignId: string; rule: Rule | null }) {
  const [state, formAction, pending] = useActionState(saveRuleAction, initialState);
  const existingModel: PayoutModel | null = rule
    ? rule.formula_version === "payout_v2"
      ? "payout_v2"
      : "payout_v1"
    : null;
  const [model, setModel] = useState<PayoutModel>(existingModel ?? "payout_v2");
  // A rule row's model is immutable: switching model creates a NEW active
  // rule (the current one is deactivated), so the rule_id is dropped.
  const replacesExisting = rule !== null && existingModel !== model;

  const d = (v: string | null | undefined) => v ?? "";

  return (
    <form
      key={`${campaignId}:${rule?.id ?? "new"}`}
      action={formAction}
      className="flex flex-col gap-6"
      noValidate
    >
      <input type="hidden" name="campaign_id" value={campaignId} />
      {rule && !replacesExisting ? (
        <input type="hidden" name="rule_id" value={rule.id} />
      ) : null}
      <input type="hidden" name="formula_version" value={model} />

      <fieldset>
        <legend className="micro text-muted mb-3">Payout model</legend>
        <div role="group" aria-label="Payout model" className="grid gap-2 sm:grid-cols-2">
          {MODEL_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setModel(option.value)}
              aria-pressed={model === option.value}
              className={cx(
                "rounded-lg border px-3.5 py-2.5 text-left text-sm transition-colors",
                model === option.value
                  ? "border-amber/60 bg-raised text-amber"
                  : "border-edge text-muted hover:border-edge-strong",
              )}
            >
              <span className="block font-medium">{option.label}</span>
              <span className="text-faint mt-0.5 block text-xs">{option.hint}</span>
            </button>
          ))}
        </div>
        {replacesExisting ? (
          <p className="micro text-amber mt-2">
            Saving creates a new active {model === "payout_v2" ? "hourly" : "per-km"} rule and
            deactivates the current one — computed payouts are never rewritten.
          </p>
        ) : null}
      </fieldset>

      {model === "payout_v2" ? (
        <fieldset className="grid gap-4 sm:grid-cols-2">
          <legend className="micro text-muted mb-3">Hourly pay (NGN · D2, D4)</legend>
          <Field
            label="Hourly rate"
            name="hourly_rate_naira"
            inputMode="decimal"
            defaultValue={existingModel === "payout_v2" ? d(rule?.hourly_rate_naira) : ""}
            placeholder="e.g. 1200"
            className="font-mono"
          />
          <Field
            label="Daily payable-hours cap"
            name="daily_payable_hours_cap"
            inputMode="decimal"
            defaultValue={
              existingModel === "payout_v2" ? d(rule?.daily_payable_hours_cap) : ""
            }
            placeholder="e.g. 8"
            className="font-mono"
          />
        </fieldset>
      ) : (
        <>
          <fieldset className="grid gap-4 sm:grid-cols-2">
            <legend className="micro text-muted mb-3">Base rates (NGN)</legend>
            <Field
              label="Per km"
              name="base_rate_per_km"
              inputMode="decimal"
              defaultValue={existingModel === "payout_v1" ? d(rule?.base_rate_per_km) : ""}
              placeholder="e.g. 55"
              className="font-mono"
            />
            <Field
              label="Per active hour"
              name="base_rate_per_active_hour"
              inputMode="decimal"
              defaultValue={
                existingModel === "payout_v1" ? d(rule?.base_rate_per_active_hour) : ""
              }
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
              defaultValue={
                existingModel === "payout_v1" ? d(rule?.target_zone_bonus_rate_per_km) : ""
              }
              placeholder="e.g. 25"
              className="font-mono"
            />
            <Field
              label="Bonus zone /km"
              name="bonus_zone_bonus_rate_per_km"
              inputMode="decimal"
              defaultValue={
                existingModel === "payout_v1" ? d(rule?.bonus_zone_bonus_rate_per_km) : ""
              }
              placeholder="e.g. 15"
              className="font-mono"
            />
            <Field
              label="Per 1,000 impressions"
              name="estimated_impression_rate_per_1000"
              inputMode="decimal"
              defaultValue={
                existingModel === "payout_v1"
                  ? d(rule?.estimated_impression_rate_per_1000)
                  : ""
              }
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
              defaultValue={existingModel === "payout_v1" ? d(rule?.min_payout_per_trip) : ""}
              placeholder="e.g. 1500"
              className="font-mono"
            />
            <Field
              label="Maximum"
              name="max_payout_per_trip"
              inputMode="decimal"
              defaultValue={existingModel === "payout_v1" ? d(rule?.max_payout_per_trip) : ""}
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
              defaultValue={existingModel === "payout_v1" ? d(rule?.low_fraud_multiplier) : ""}
              placeholder="0.90"
              className="font-mono"
            />
            <Field
              label="Medium severity"
              name="medium_fraud_multiplier"
              inputMode="decimal"
              defaultValue={
                existingModel === "payout_v1" ? d(rule?.medium_fraud_multiplier) : ""
              }
              placeholder="0.70"
              className="font-mono"
            />
            <Field
              label="High severity"
              name="high_fraud_multiplier"
              inputMode="decimal"
              defaultValue={existingModel === "payout_v1" ? d(rule?.high_fraud_multiplier) : ""}
              placeholder="0.25"
              className="font-mono"
            />
          </fieldset>
        </>
      )}

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
        {pending
          ? "Saving…"
          : rule && !replacesExisting
            ? "Update rule"
            : "Create rule"}
      </Button>
      <p className="micro text-faint">
        {model === "payout_v2"
          ? "Pay = hourly rate × verified payable time, truncated at the daily cap before pricing. Already-calculated payouts are never rewritten."
          : "Empty fields fall back to platform defaults. Already-calculated payouts are never rewritten — rules apply from the next calculation onward."}
      </p>
    </form>
  );
}
