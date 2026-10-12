import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Steps } from "@/components/ui/steps";
import type { DriverCampaignJourney, JourneyStepState } from "@/lib/driver/campaign-journey";

const stateLabel: Record<JourneyStepState, string> = {
  complete: "Done",
  current: "Now",
  pending: "Waiting",
  blocked: "Needs action",
  degraded: "Can't check",
};

const stateTone: Record<JourneyStepState, "green" | "cyan" | "amber" | "coral" | "default"> = {
  complete: "green",
  current: "cyan",
  pending: "amber",
  blocked: "coral",
  degraded: "default",
};

export const standingLabel: Record<DriverCampaignJourney["standing"], string> = {
  READY: "Set up",
  TRACKING: "On a trip",
  PENDING: "Not ready yet",
  BLOCKED: "Needs action",
  DEGRADED: "Can't check",
};

export const standingTone = {
  READY: "green",
  TRACKING: "cyan",
  PENDING: "amber",
  BLOCKED: "coral",
  DEGRADED: "default",
} as const;

/** The driver's setup checklist, shown while something still stands between them and a trip. */
export function CampaignJourneyPanel({ journey }: { journey: DriverCampaignJourney }) {
  return (
    <Panel className="p-5" aria-labelledby="campaign-journey-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="campaign-journey-title" className="font-display text-lg font-semibold">
            Getting ready to drive
          </h2>
          <p className="text-muted mt-1 text-sm leading-5">{journey.summary}</p>
        </div>
        <StatusChip tone={standingTone[journey.standing]}>
          {standingLabel[journey.standing]}
        </StatusChip>
      </div>
      <div className="mt-4">
        <Steps
          label="Setup steps"
          items={journey.steps.map((step) => ({
            key: step.id,
            href: step.href,
            current: step.state === "current",
            title: step.title,
            detail: step.detail,
            badge: <StatusChip tone={stateTone[step.state]}>{stateLabel[step.state]}</StatusChip>,
          }))}
        />
      </div>
    </Panel>
  );
}
