"use client";

import { useState, useTransition } from "react";
import { statusActions, type CampaignStatus } from "@/lib/campaigns/status";
import { updateCampaignStatusAction } from "./actions";
import { cx } from "@/lib/cx";

/**
 * Status transition buttons. Destructive transitions ask for confirmation;
 * everything disables while the action is in flight so double-submits
 * can't race the backend.
 */
export function StatusActions({
  campaignId,
  status,
  productionAuthorized,
}: {
  campaignId: string;
  status: CampaignStatus;
  productionAuthorized: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | undefined>();
  const actions = statusActions[status].filter(
    (action) => action.to !== "active" || productionAuthorized,
  );

  if (actions.length === 0 && productionAuthorized) return null;

  function run(to: CampaignStatus, destructive?: boolean) {
    if (destructive && !window.confirm("This cannot be undone from the dashboard. Continue?")) {
      return;
    }
    setError(undefined);
    startTransition(async () => {
      const result = await updateCampaignStatusAction({ campaignId, to });
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <button
            key={a.to}
            type="button"
            disabled={pending}
            onClick={() => run(a.to, a.destructive)}
            className={cx(
              "micro rounded-lg border px-3.5 py-2.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50",
              a.destructive
                ? "border-coral/40 bg-coral/10 text-coral hover:bg-coral/15"
                : "border-edge bg-raised text-ink hover:border-edge-strong",
            )}
          >
            {pending ? "…" : a.label}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
      {!productionAuthorized && ["draft", "scheduled", "paused"].includes(status) ? (
        <p className="text-amber max-w-xs text-right text-xs">
          Launch and resume unlock after funding and production authority are recorded.
        </p>
      ) : null}
    </div>
  );
}
