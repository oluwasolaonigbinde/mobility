import Link from "next/link";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import type { DriverCampaignJourney, JourneyStepState } from "@/lib/driver/campaign-journey";

const stateLabel: Record<JourneyStepState, string> = {
  complete: "Complete",
  current: "Current",
  pending: "Pending",
  blocked: "Blocked",
  degraded: "Unavailable",
};

const stateTone: Record<JourneyStepState, "green" | "cyan" | "amber" | "coral" | "default"> = {
  complete: "green",
  current: "cyan",
  pending: "amber",
  blocked: "coral",
  degraded: "default",
};

const standingTone = {
  READY: "green",
  TRACKING: "cyan",
  PENDING: "amber",
  BLOCKED: "coral",
  DEGRADED: "default",
} as const;

export function CampaignJourneyPanel({
  journey,
  compact = false,
}: {
  journey: DriverCampaignJourney;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <Panel
        className="flex items-start justify-between gap-4 p-4"
        aria-label="Campaign journey status"
      >
        <div>
          <p className="micro text-muted">Campaign journey</p>
          <p className="text-muted mt-1 text-xs leading-5">{journey.summary}</p>
        </div>
        <StatusChip tone={standingTone[journey.standing]}>{journey.standing}</StatusChip>
      </Panel>
    );
  }

  return (
    <Panel className="p-5" aria-labelledby="campaign-journey-title">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="micro text-muted">Onboarding to tracking</p>
          <h2 id="campaign-journey-title" className="font-display mt-1 text-lg font-semibold">
            Your campaign journey
          </h2>
          <p className="text-muted mt-1 text-xs leading-5">{journey.summary}</p>
        </div>
        <StatusChip tone={standingTone[journey.standing]}>{journey.standing}</StatusChip>
      </div>
      <ol className="mt-5 space-y-3">
        {journey.steps.map((step, index) => (
          <li key={step.id}>
            <Link
              href={step.href}
              aria-current={step.state === "current" ? "step" : undefined}
              className="border-edge bg-raised focus:border-amber flex items-start gap-3 rounded-lg border p-3 focus:outline-none"
            >
              <span
                aria-hidden
                className="bg-bg text-muted flex size-7 shrink-0 items-center justify-center rounded-full font-mono text-xs"
              >
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium">{step.label}</span>
                  <StatusChip tone={stateTone[step.state]}>{stateLabel[step.state]}</StatusChip>
                </span>
                <span className="mt-1 block text-xs font-medium">{step.title}</span>
                <span className="text-faint mt-0.5 block text-xs leading-5">{step.detail}</span>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
