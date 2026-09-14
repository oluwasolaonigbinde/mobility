import type { components } from "@/lib/api/schema";
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

function nextAction(campaign: Campaign, commercial: Commercial, creatives: Creative[]): string {
  if (campaign.status === "rejected") return "Update the rejected campaign details, then resubmit.";
  if (!commercial.quote_request) return "Request the custom quotation for this campaign.";
  if (!commercial.revisions.length) return "Wait for Cardvert to post the quotation for review.";
  if (!commercial.terms) return "Review and accept the latest quotation shown below.";
  if (!creatives.length) return "Add the artwork files required for this campaign.";
  if (creatives.some((creative) => creative.status === "rejected")) {
    return "Replace or update rejected artwork, then resubmit it for review.";
  }
  if (creatives.some((creative) => creative.status === "draft")) {
    return "Submit each draft artwork file for Cardvert review.";
  }
  if (creatives.some((creative) => creative.status === "pending_review")) {
    return "Wait for Cardvert to finish the artwork review.";
  }
  if (!commercial.financial_authority) {
    return "Wait for Cardvert to record the applicable funding or approved credit authority.";
  }
  if (campaign.status === "draft") return "Submit the completed campaign for Cardvert review.";
  if (campaign.status === "pending_review") return "Wait for Cardvert to finish campaign review.";
  if (campaign.status === "active")
    return "This campaign is active; review delivery results below.";
  if (campaign.status === "paused")
    return "This campaign is paused; Cardvert controls any approved resume.";
  if (campaign.status === "completed")
    return "This campaign is complete; review the issued analysis.";
  if (campaign.status === "cancelled") return "This campaign is cancelled; no new work can start.";
  return "Cardvert controls scheduling, assignment, installation evidence and activation.";
}

export function CampaignPreparationSummary({
  campaign,
  commercial,
  creatives,
}: {
  campaign: Campaign;
  commercial?: Commercial;
  creatives?: Creative[];
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
  return (
    <Panel className="mb-6 p-5" aria-label="Campaign preparation">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Campaign preparation</h2>
          <p className="text-muted mt-1 text-sm">
            Next action: {nextAction(campaign, commercial, creatives)}
          </p>
        </div>
        <StatusChip tone={campaign.status === "active" ? "green" : "amber"}>
          {campaign.status === "active" ? "Active" : "Preparation in progress"}
        </StatusChip>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="micro text-muted">Campaign review</dt>
          <dd className="mt-1">{campaign.status.replaceAll("_", " ")}</dd>
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
      <p className="text-faint mt-4 text-xs">
        This summary uses recorded campaign, quotation, artwork and funding facts only. It does not
        authorize production, assignment, installation or launch.
      </p>
    </Panel>
  );
}
