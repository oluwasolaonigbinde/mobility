import type { components } from "@/lib/api/schema";
import { statusLabel, statusTone } from "@/lib/campaigns/status";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

type Campaign = components["schemas"]["CampaignRead"];
type Commercial = components["schemas"]["CampaignCommercialRead"];
type Creative = components["schemas"]["CreativeRead"];

function quoteState(commercial: Commercial): string {
  if (commercial.terms) return "Accepted";
  if (commercial.revisions.length) return "Review required";
  if (commercial.quote_request) return "Being prepared";
  return "Not requested";
}

function artworkState(creatives: Creative[]): string {
  if (!creatives.length) return "Not added";
  if (creatives.some((creative) => creative.status === "rejected")) return "Changes required";
  if (creatives.some((creative) => creative.status === "draft")) return "Submit for review";
  if (creatives.some((creative) => creative.status === "pending_review")) return "Under review";
  if (creatives.every((creative) => creative.status === "approved")) return "Approved";
  return "Not ready";
}

// Once a campaign is running or finished, its lifecycle — not a preparation step —
// is the useful next action.
const lifecycleAction: Partial<Record<Campaign["status"], string>> = {
  active:
    "This campaign is live. Results appear on the Campaign Performance Analysis page once Terrax Media issues a report.",
  paused: "This campaign is paused. Terrax Media decides when it can resume.",
  completed:
    "This campaign has finished. Its report appears on the Campaign Performance Analysis page once issued.",
  cancelled: "This campaign is cancelled; no new work can start.",
};

function nextAction(campaign: Campaign, commercial: Commercial, creatives: Creative[]): string {
  const lifecycle = lifecycleAction[campaign.status];
  if (lifecycle) return lifecycle;
  if (campaign.status === "rejected") return "Update the rejected campaign details, then resubmit.";
  if (!commercial.quote_request) return "Request the custom quotation for this campaign.";
  if (!commercial.revisions.length)
    return "Wait for Terrax Media to post the quotation for review.";
  if (!commercial.terms) return "Review and accept the latest quotation shown below.";
  if (!creatives.length) return "Add the artwork files required for this campaign.";
  if (creatives.some((creative) => creative.status === "rejected")) {
    return "Replace or update rejected artwork, then resubmit it for review.";
  }
  if (creatives.some((creative) => creative.status === "draft")) {
    return "Submit each draft artwork file for Terrax Media to review.";
  }
  if (creatives.some((creative) => creative.status === "pending_review")) {
    return "Wait for Terrax Media to finish the artwork review.";
  }
  if (!commercial.financial_authority) {
    return "Wait for Terrax Media to confirm your payment or agreed credit.";
  }
  if (campaign.status === "draft")
    return "Submit the completed campaign for Terrax Media to review.";
  if (campaign.status === "pending_review")
    return "Wait for Terrax Media to finish the campaign review.";
  return "Terrax Media now arranges drivers, installation and the start date.";
}

// D38(d): the server refuses review until these exist; say so before the button is pressed.
function missingForReview(campaign: Campaign, targetAreas?: number): string[] {
  if (campaign.status !== "draft" && campaign.status !== "rejected") return [];
  const missing: string[] = [];
  if (!campaign.start_at || !campaign.end_at) missing.push("start and end dates");
  if (!campaign.budget_amount || Number(campaign.budget_amount) <= 0)
    missing.push("a total budget");
  if (targetAreas === 0) missing.push("a target area");
  return missing;
}

export function CampaignPreparationSummary({
  campaign,
  commercial,
  creatives,
  targetAreas,
}: {
  campaign: Campaign;
  commercial?: Commercial;
  creatives?: Creative[];
  /** Target-area count from the campaign's target-zone list; undefined when it couldn't be read. */
  targetAreas?: number;
}) {
  if (!commercial || !creatives) {
    return (
      <Panel className="border-amber/40 bg-amber/5 mb-6 p-5" aria-label="Campaign preparation">
        <h2 className="font-display text-lg font-semibold">Campaign preparation</h2>
        <p className="text-muted mt-2 text-sm">
          Some preparation details are unavailable, so Cardvert is not showing a readiness
          conclusion. Retry the unavailable section below.
        </p>
      </Panel>
    );
  }

  const artwork = artworkState(creatives);
  const missing = missingForReview(campaign, targetAreas);
  return (
    <Panel className="mb-6 p-5" aria-label="Campaign preparation">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Campaign preparation</h2>
          <p className="text-muted mt-1 text-sm">
            Next action: {nextAction(campaign, commercial, creatives)}
          </p>
        </div>
        {lifecycleAction[campaign.status] ? (
          <StatusChip tone={statusTone[campaign.status]}>{statusLabel[campaign.status]}</StatusChip>
        ) : (
          <StatusChip tone="amber">Preparation in progress</StatusChip>
        )}
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="micro text-muted">Campaign review</dt>
          <dd className="mt-1">{statusLabel[campaign.status]}</dd>
        </div>
        <div>
          <dt className="micro text-muted">Quotation</dt>
          <dd className="mt-1">{quoteState(commercial)}</dd>
        </div>
        <div>
          <dt className="micro text-muted">Artwork</dt>
          <dd className="mt-1">{artwork}</dd>
        </div>
        <div>
          <dt className="micro text-muted">Funding / credit</dt>
          <dd className="mt-1">
            {commercial.financial_authority ? "Recorded" : "Not yet recorded"}
          </dd>
        </div>
      </dl>
      {missing.length ? (
        <p className="text-coral mt-4 text-sm">
          Before you can submit for review, add{" "}
          {missing.length > 1
            ? `${missing.slice(0, -1).join(", ")} and ${missing.at(-1)}`
            : missing[0]}
          .
        </p>
      ) : null}
      <p className="text-faint mt-4 text-xs">
        This checklist shows what has been recorded so far. It does not authorize production,
        assignment, installation or launch.
      </p>
    </Panel>
  );
}
