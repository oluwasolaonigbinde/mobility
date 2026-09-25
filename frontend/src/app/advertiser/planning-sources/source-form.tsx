"use client";

import { useActionState, useState } from "react";
import { createSourceAction, type SourceActionState } from "./actions";
import { labelFor, optionLabel, sourceTypeLabel } from "./labels";
import { ensureOperationKey, stableOperationKey } from "./operation-form";

const initialState: SourceActionState = {};

const selectClass = "border-edge bg-bg max-w-full min-w-0 rounded-lg border px-3 py-2";

function Options({ values }: { values: string[] }) {
  return (
    <>
      {values.map((value) => (
        <option key={value} value={value}>
          {labelFor(optionLabel, value)}
        </option>
      ))}
    </>
  );
}

export function SourceForm() {
  const [sourceType, setSourceType] = useState("website-traffic");
  const [state, action, pending] = useActionState(createSourceAction, initialState);
  const operation = stableOperationKey(state);
  const website = sourceType === "website-traffic";
  const digital = sourceType === "digital-campaign-audience";
  const crm = sourceType === "CRM-upload-reference";
  const utm = sourceType === "UTM-source";
  const manual = sourceType === "manual-insight";

  return (
    <form
      action={action}
      onSubmit={ensureOperationKey}
      className="grid min-w-0 gap-4"
      data-testid="planning-source-form"
    >
      <input
        key={operation.inputKey}
        type="hidden"
        name="operation_key"
        defaultValue={operation.defaultValue}
      />
      <label className="grid gap-1 text-sm">
        <span className="text-muted">What kind of audience is it?</span>
        <select
          name="source_type"
          value={sourceType}
          onChange={(event) => setSourceType(event.target.value)}
          className={selectClass}
        >
          {Object.entries(sourceTypeLabel).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {website || manual ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">What do they have in common?</span>
          <select name="category" className={selectClass}>
            <Options
              values={
                website
                  ? ["site-visitor", "content-interest", "conversion-intent"]
                  : ["area-demand", "time-pattern", "contextual-affinity"]
              }
            />
          </select>
        </label>
      ) : null}
      {digital || utm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Where did they come from?</span>
          <select name="channel" className={selectClass}>
            <Options values={["search", "social", "display", ...(utm ? ["email"] : [])]} />
          </select>
        </label>
      ) : null}
      {digital || utm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">
            {utm ? "Which campaign stage is it for?" : "How close are they to buying?"}
          </span>
          <select name="stage" className={selectClass}>
            <Options values={["awareness", "consideration", "conversion-intent"]} />
          </select>
        </label>
      ) : null}
      {website || digital ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Covering the last (days)</span>
          <input
            name="window_days"
            type="number"
            min="1"
            max="365"
            defaultValue="30"
            required
            className={selectClass}
          />
        </label>
      ) : null}
      {crm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">About how many people?</span>
          <select name="count_band" className={selectClass}>
            <Options values={["0-99", "100-999", "1000-plus"]} />
          </select>
        </label>
      ) : null}
      {manual ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">How confident are you?</span>
          <select name="confidence" className={selectClass}>
            <Options values={["low", "medium", "high"]} />
          </select>
        </label>
      ) : null}
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Stop using this description on</span>
        <input name="expires_at" type="datetime-local" required className={selectClass} />
      </label>
      <p className="micro text-faint">
        Choose categories only. Names, emails, phone numbers, links, notes and files are not
        accepted. The legal basis and privacy notice for using this information have not been
        approved yet, so downloads stay off until that approval is in place.
      </p>
      {state.error ? (
        <p className="text-coral text-sm" role="alert">
          {state.error}
        </p>
      ) : null}
      {state.success ? (
        <p className="text-success text-sm" role="status">
          {state.success}
        </p>
      ) : null}
      <button
        disabled={pending}
        className="bg-amber text-bg rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {pending ? "Saving…" : "Save audience"}
      </button>
    </form>
  );
}
