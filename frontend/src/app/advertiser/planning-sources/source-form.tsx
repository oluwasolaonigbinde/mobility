"use client";

import { useActionState, useState } from "react";
import { createSourceAction, type SourceActionState } from "./actions";
import { ensureOperationKey, stableOperationKey } from "./operation-form";

const initialState: SourceActionState = {};

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
      className="grid gap-4"
      data-testid="planning-source-form"
    >
      <input
        key={operation.inputKey}
        type="hidden"
        name="operation_key"
        defaultValue={operation.defaultValue}
      />
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Source type</span>
        <select
          name="source_type"
          value={sourceType}
          onChange={(event) => setSourceType(event.target.value)}
          className="border-edge bg-bg rounded-lg border px-3 py-2"
        >
          <option value="website-traffic">Website traffic</option>
          <option value="digital-campaign-audience">Digital campaign audience</option>
          <option value="CRM-upload-reference">CRM aggregate reference</option>
          <option value="UTM-source">UTM source</option>
          <option value="manual-insight">Manual aggregate insight</option>
        </select>
      </label>
      {website || manual ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Category</span>
          <select name="category" className="border-edge bg-bg rounded-lg border px-3 py-2">
            {(website
              ? ["site-visitor", "content-interest", "conversion-intent"]
              : ["area-demand", "time-pattern", "contextual-affinity"]
            ).map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      ) : null}
      {digital || utm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Channel</span>
          <select name="channel" className="border-edge bg-bg rounded-lg border px-3 py-2">
            {["search", "social", "display", ...(utm ? ["email"] : [])].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      ) : null}
      {digital || utm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Stage</span>
          <select name="stage" className="border-edge bg-bg rounded-lg border px-3 py-2">
            {["awareness", "consideration", "conversion-intent"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      ) : null}
      {website || digital ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Aggregate window (days)</span>
          <input
            name="window_days"
            type="number"
            min="1"
            max="365"
            defaultValue="30"
            required
            className="border-edge bg-bg rounded-lg border px-3 py-2"
          />
        </label>
      ) : null}
      {crm ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Record-count band</span>
          <select name="count_band" className="border-edge bg-bg rounded-lg border px-3 py-2">
            {["0-99", "100-999", "1000-plus"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      ) : null}
      {manual ? (
        <label className="grid gap-1 text-sm">
          <span className="text-muted">Confidence band</span>
          <select name="confidence" className="border-edge bg-bg rounded-lg border px-3 py-2">
            {["low", "medium", "high"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Expiry</span>
        <input
          name="expires_at"
          type="datetime-local"
          required
          className="border-edge bg-bg rounded-lg border px-3 py-2"
        />
      </label>
      <p className="micro text-faint">
        Only aggregate planning facts are accepted. Identifiers, uploads, URLs and notes are
        rejected. Lawful-basis and notice status remain unapproved pending client legal evidence.
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
        {pending ? "Recording…" : "Record source"}
      </button>
    </form>
  );
}
