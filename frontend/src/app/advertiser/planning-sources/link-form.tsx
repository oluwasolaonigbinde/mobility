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

const fieldClass = "border-edge bg-bg max-w-full min-w-0 rounded-lg border px-3 py-2";

function missingPrerequisite(
  sources: SourceOption[],
  campaigns: CampaignOption[],
  targetZones: ZoneOption[],
  zonesIncomplete: boolean,
): string | null {
  if (sources.length === 0) return "Describe an audience first.";
  if (campaigns.length === 0) return "Create a campaign first.";
  if (targetZones.length === 0) {
    return zonesIncomplete
      ? "Campaign areas couldn't be loaded. Refresh the page to try again."
      : "This campaign has no areas yet. Add one from the campaign's Zones page.";
  }
  return null;
}

export function LinkForm({
  sources,
  campaigns,
  zones,
  zonesIncomplete = false,
}: {
  sources: SourceOption[];
  campaigns: CampaignOption[];
  zones: ZoneOption[];
  zonesIncomplete?: boolean;
}) {
  const [campaignId, setCampaignId] = useState(campaigns[0]?.id ?? "");
  const [state, action, pending] = useActionState(createSourceLinkAction, initialState);
  const operation = stableOperationKey(state);
  const targetZones = useMemo(
    () => zones.filter((zone) => zone.campaignId === campaignId),
    [campaignId, zones],
  );
  const missing = missingPrerequisite(sources, campaigns, targetZones, zonesIncomplete);

  return (
    <form
      action={action}
      onSubmit={ensureOperationKey}
      className="grid min-w-0 gap-4"
      data-testid="planning-source-link-form"
    >
      <input
        key={operation.inputKey}
        type="hidden"
        name="operation_key"
        defaultValue={operation.defaultValue}
      />
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Audience</span>
        <select name="source_id" required className={fieldClass}>
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
          className={fieldClass}
        >
          {campaigns.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Campaign area</span>
        <select name="zone_id" required className={fieldClass}>
          {targetZones.map((zone) => (
            <option key={zone.id} value={zone.id}>
              {zone.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">From</span>
        <input name="start_at" type="datetime-local" required className={fieldClass} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="text-muted">Until</span>
        <input name="end_at" type="datetime-local" required className={fieldClass} />
      </label>
      <p className="micro text-faint">
        Pick dates inside the campaign&apos;s dates and before the audience description stops being
        used.
      </p>
      {missing ? (
        <p id="link-form-missing" className="text-amber text-sm">
          {missing}
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
        disabled={pending || missing !== null}
        aria-describedby={missing ? "link-form-missing" : undefined}
        className="bg-amber text-bg rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {pending ? "Connecting…" : "Connect"}
      </button>
    </form>
  );
}
