"use client";

import { useActionState, useMemo, useState } from "react";
import { createSourceLinkAction, type SourceActionState } from "./actions";
import { ensureOperationKey, stableOperationKey } from "./operation-form";

interface SourceOption {
  id: string;
  label: string;
}

interface CampaignOption {
  id: string;
  label: string;
}

interface ZoneOption {
  id: string;
  campaignId: string;
  label: string;
}

const initialState: SourceActionState = {};

export function LinkForm({
  sources,
  campaigns,
  zones,
}: {
  sources: SourceOption[];
  campaigns: CampaignOption[];
  zones: ZoneOption[];
}) {
  const [campaignId, setCampaignId] = useState(campaigns[0]?.id ?? "");
  const [state, action, pending] = useActionState(createSourceLinkAction, initialState);
  const operation = stableOperationKey(state);
  const targetZones = useMemo(
    () => zones.filter((zone) => zone.campaignId === campaignId),
    [campaignId, zones],
  );
  const unavailable = sources.length === 0 || campaigns.length === 0 || targetZones.length === 0;

  return (
    <form
      action={action}
      onSubmit={ensureOperationKey}
      className="grid gap-4"
      data-testid="planning-source-link-form"
    >
      <input
        key={operation.inputKey}
        type="hidden"
        name="operation_key"
        defaultValue={operation.defaultValue}
      />
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Source</span>
        <select name="source_id" required className="border-edge bg-bg rounded-lg border px-3 py-2">
          {sources.map((source) => (
            <option key={source.id} value={source.id}>
              {source.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Campaign</span>
        <select
          name="campaign_id"
          required
          value={campaignId}
          onChange={(event) => setCampaignId(event.target.value)}
          className="border-edge bg-bg rounded-lg border px-3 py-2"
        >
          {campaigns.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Target zone</span>
        <select name="zone_id" required className="border-edge bg-bg rounded-lg border px-3 py-2">
          {targetZones.map((zone) => (
            <option key={zone.id} value={zone.id}>
              {zone.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Start</span>
        <input
          name="start_at"
          type="datetime-local"
          required
          className="border-edge bg-bg rounded-lg border px-3 py-2"
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">End</span>
        <input
          name="end_at"
          type="datetime-local"
          required
          className="border-edge bg-bg rounded-lg border px-3 py-2"
        />
      </label>
      <p className="micro text-faint">
        Only owned active sources, campaigns and target zones are accepted. The window must remain
        inside campaign and source expiry bounds.
      </p>
      {unavailable ? (
        <p className="text-amber text-sm">
          Create an active source, campaign and target zone first.
        </p>
      ) : null}
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
        disabled={pending || unavailable}
        className="bg-amber text-bg rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {pending ? "Linking…" : "Link source"}
      </button>
    </form>
  );
}
