import Link from "next/link";
import { formatDateRange } from "@/lib/format";
import { campaignDay } from "@/lib/campaigns/day-progress";
import { PortalIcon } from "@/components/brand/portal-icon";
import { isCampaignStatus, statusLabel } from "@/lib/campaigns/status";

type Campaign = {
  id: string;
  name: string;
  status: string;
  start_at: string | null;
  end_at: string | null;
};
/** A dated list, with extensions already reflected in the campaign's own dates. */
export function CampaignTimeline({ campaigns }: { campaigns: Campaign[] }) {
  const dated = campaigns
    .filter(
      (campaign) =>
        campaign.start_at &&
        campaign.end_at &&
        ["active", "paused", "approved", "finished"].includes(campaign.status),
    )
    .sort((a, b) => a.start_at!.localeCompare(b.start_at!));
  if (!dated.length) return null;
  return (
    <section
      className="border-edge mb-6 rounded-2xl border bg-white p-5"
      aria-label="Campaign timeline"
    >
      <h2 className="font-display mb-4 flex items-center gap-2 text-lg font-semibold">
        <PortalIcon name="calendar" />
        Campaign timeline
      </h2>
      <ol className="grid max-h-80 gap-3 overflow-y-auto">
        {dated.map((campaign) => (
          <li
            key={campaign.id}
            className="border-green/30 grid gap-1 border-l-2 pl-4 sm:grid-cols-[1fr_auto]"
          >
            <Link
              href={`/advertiser/campaigns/${campaign.id}`}
              className="hover:text-green text-sm font-semibold"
            >
              {campaign.name}
            </Link>
            <p className="text-muted text-sm">
              {formatDateRange(campaign.start_at, campaign.end_at)}
            </p>
            <p className="text-green text-xs">
              {isCampaignStatus(campaign.status) ? statusLabel[campaign.status] : ""} ·{" "}
              {campaignDay(campaign.start_at, campaign.end_at)}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
